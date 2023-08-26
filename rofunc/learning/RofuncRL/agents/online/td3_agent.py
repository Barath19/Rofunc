# Copyright 2023, Junjia LIU, jjliu@mae.cuhk.edu.hk
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import gym
import gymnasium
import itertools
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import DictConfig
from typing import Union, Tuple, Optional

import rofunc as rf
from rofunc.learning.RofuncRL.agents.base_agent import BaseAgent
from rofunc.learning.RofuncRL.models.actor_models import ActorTD3
from rofunc.learning.RofuncRL.models.critic_models import Critic
from rofunc.learning.RofuncRL.processors.noises import GaussianNoise
from rofunc.learning.RofuncRL.processors.schedulers import KLAdaptiveRL
from rofunc.learning.RofuncRL.processors.standard_scaler import RunningStandardScaler
from rofunc.learning.RofuncRL.processors.standard_scaler import empty_preprocessor
from rofunc.learning.RofuncRL.utils.memory import Memory


class TD3Agent(BaseAgent):
    def __init__(self,
                 cfg: DictConfig,
                 observation_space: Optional[Union[int, Tuple[int], gym.Space, gymnasium.Space]],
                 action_space: Optional[Union[int, Tuple[int], gym.Space, gymnasium.Space]],
                 memory: Optional[Union[Memory, Tuple[Memory]]] = None,
                 device: Optional[Union[str, torch.device]] = None,
                 experiment_dir: Optional[str] = None,
                 rofunc_logger: Optional[rf.logger.BeautyLogger] = None):
        """
        Twin Delayed Deep Deterministic Policy Gradient (TD3) agent
        “Addressing Function Approximation Error in Actor-Critic Methods”. Fujimoto. et al. 2018. https://arxiv.org/abs/1802.09477
        Rofunc documentation: https://rofunc.readthedocs.io/en/latest/lfd/RofuncRL/TD3.html
        :param cfg: Custom configuration
        :param observation_space: Observation/state space or shape
        :param action_space: Action space or shape
        :param memory: Memory for storing transitions
        :param device: Device on which the torch tensor is allocated
        :param experiment_dir: Directory where experiment outputs are saved
        :param rofunc_logger: Rofunc logger
        """
        super().__init__(cfg, observation_space, action_space, memory, device, experiment_dir, rofunc_logger)

        '''Define models for TD3'''
        concat_space = [observation_space, action_space]
        self.actor = ActorTD3(cfg.Model, observation_space, action_space, self.se).to(self.device)
        self.target_actor = ActorTD3(cfg.Model, observation_space, action_space, self.se).to(self.device)
        self.critic_1 = Critic(cfg.Model, concat_space, action_space, self.se).to(self.device)
        self.critic_2 = Critic(cfg.Model, concat_space, action_space, self.se).to(self.device)
        self.target_critic_1 = Critic(cfg.Model, concat_space, action_space, self.se).to(self.device)
        self.target_critic_2 = Critic(cfg.Model, concat_space, action_space, self.se).to(self.device)

        self.models = {"actor": self.actor, "target_actor": self.target_actor, "critic_1": self.critic_1,
                       "critic_2": self.critic_2, "target_critic_1": self.target_critic_1,
                       "target_critic_2": self.target_critic_2}

        # checkpoint models
        self.checkpoint_modules["actor"] = self.actor
        self.checkpoint_modules["target_actor"] = self.target_actor
        self.checkpoint_modules["critic_1"] = self.critic_1
        self.checkpoint_modules["critic_2"] = self.critic_2
        self.checkpoint_modules["target_critic_1"] = self.target_critic_1
        self.checkpoint_modules["target_critic_2"] = self.target_critic_2

        self.rofunc_logger.module(f"Actor model: {self.actor}")
        self.rofunc_logger.module(f"Critic model x4: {self.critic_1}")

        '''Create tensors in memory'''
        if hasattr(cfg.Model, "state_encoder"):
            img_channel = int(self.cfg.Model.state_encoder.inp_channels)
            img_size = int(self.cfg.Model.state_encoder.image_size)
            state_tensor_size = (img_channel, img_size, img_size)
            kd = True
        else:
            state_tensor_size = self.observation_space
            kd = False
        self.memory.create_tensor(name="states", size=state_tensor_size, dtype=torch.float32, keep_dimensions=kd)
        self.memory.create_tensor(name="next_states", size=state_tensor_size, dtype=torch.float32, keep_dimensions=kd)
        self.memory.create_tensor(name="actions", size=self.action_space, dtype=torch.float32)
        self.memory.create_tensor(name="rewards", size=1, dtype=torch.float32)
        self.memory.create_tensor(name="terminated", size=1, dtype=torch.bool)
        self._tensors_names = ["states", "actions", "rewards", "next_states", "terminated"]

        '''Get hyper-parameters from config'''
        self._discount = self.cfg.Agent.discount
        self._gradient_steps = self.cfg.Agent.gradient_steps
        self._polyak = self.cfg.Agent.polyak
        self._batch_size = self.cfg.Agent.batch_size
        self._lr_a = self.cfg.Agent.lr_a
        self._lr_c = self.cfg.Agent.lr_c
        self._lr_scheduler = self.cfg.get("Agent", {}).get("lr_scheduler", KLAdaptiveRL)
        self._lr_scheduler_kwargs = self.cfg.get("Agent", {}).get("lr_scheduler_kwargs", {'kl_threshold': 0.008})
        self._adam_eps = self.cfg.Agent.adam_eps
        self._grad_norm_clip = self.cfg.Agent.grad_norm_clip
        self._kl_threshold = self.cfg.Agent.kl_threshold

        self._policy_update_delay = self.cfg.Agent.policy_update_delay
        self._smooth_regularization_noise = GaussianNoise(0, 0.1, device=device)
        self._smooth_regularization_clip = self.cfg.Agent.smooth_regularization_clip
        self._rewards_shaper = self.cfg.get("Agent", {}).get("rewards_shaper", lambda rewards: rewards * 0.01)
        self._state_preprocessor = RunningStandardScaler
        self._state_preprocessor_kwargs = self.cfg.get("Agent", {}).get("state_preprocessor_kwargs",
                                                                        {"size": observation_space, "device": device})

        '''Misc variables'''
        self._current_log_prob = None
        self._current_next_states = None
        self._critic_update_times = 0
        # clip noise bounds
        if action_space is not None:
            self.clip_actions_min = torch.tensor(action_space.low, device=self.device)
            self.clip_actions_max = torch.tensor(action_space.high, device=self.device)

        self._set_up()

    def _set_up(self):
        """
        Set up optimizer, learning rate scheduler and state/value preprocessors
        """
        # Set up optimizer and learning rate scheduler
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=self._lr_a, eps=self._adam_eps)
        self.critic_optimizer = torch.optim.Adam(
            itertools.chain(self.critic_1.parameters(), self.critic_2.parameters()), lr=self._lr_c, eps=self._adam_eps)
        if self._lr_scheduler is not None:
            self.actor_scheduler = self._lr_scheduler(self.actor_optimizer, **self._lr_scheduler_kwargs)
            self.critic_scheduler = self._lr_scheduler(self.critic_optimizer, **self._lr_scheduler_kwargs)
        self.checkpoint_modules["actor_optimizer"] = self.actor_optimizer
        self.checkpoint_modules["critic_optimizer"] = self.critic_optimizer

        # freeze target networks with respect to optimizers (update via .update_parameters())
        self.target_actor.freeze_parameters(True)
        self.target_critic_1.freeze_parameters(True)
        self.target_critic_2.freeze_parameters(True)
        # update target networks (hard update)
        self.target_actor.update_parameters(self.actor, polyak=1)
        self.target_critic_1.update_parameters(self.critic_1, polyak=1)
        self.target_critic_2.update_parameters(self.critic_2, polyak=1)
        
        # set up preprocessors
        super()._set_up()

    def act(self, states: torch.Tensor, deterministic: bool = False):
        if not deterministic:
            # sample stochastic actions
            actions, _ = self.actor(self._state_preprocessor(states))
        else:
            # choose deterministic actions for evaluation TODO: check if this is correct
            actions, _ = self.actor(self._state_preprocessor(states)).detach()
        return actions, None

    def store_transition(self, states: torch.Tensor, actions: torch.Tensor, next_states: torch.Tensor,
                         rewards: torch.Tensor, terminated: torch.Tensor, truncated: torch.Tensor, infos: torch.Tensor):
        super().store_transition(states=states, actions=actions, next_states=next_states, rewards=rewards,
                                 terminated=terminated, truncated=truncated, infos=infos)

        # reward shaping
        if self._rewards_shaper is not None:
            rewards = self._rewards_shaper(rewards)

        # storage transition in memory
        self.memory.add_samples(states=states, actions=actions, rewards=rewards, next_states=next_states,
                                terminated=terminated, truncated=truncated)

    def update_net(self):
        """
        Update the network
        :return:
        """
        # sample a batch from memory
        sampled_states, sampled_actions, sampled_rewards, sampled_next_states, sampled_dones = \
            self.memory.sample(names=self._tensors_names, batch_size=self._batch_size)[0]

        # learning epochs
        for gradient_step in range(self._gradient_steps):
            sampled_states = self._state_preprocessor(sampled_states, train=not gradient_step)
            sampled_next_states = self._state_preprocessor(sampled_next_states)

            with torch.no_grad():
                # target policy smoothing
                next_actions, _ = self.target_actor(sampled_next_states)
                noises = torch.clamp(self._smooth_regularization_noise.sample(next_actions.shape),
                                     min=-self._smooth_regularization_clip,
                                     max=self._smooth_regularization_clip)
                next_actions.add_(noises)
                next_actions.clamp_(min=self.clip_actions_min, max=self.clip_actions_max)

                # compute target values
                target_q1_values = self.target_critic_1(sampled_next_states, next_actions)
                target_q2_values = self.target_critic_2(sampled_next_states, next_actions)
                target_q_values = torch.min(target_q1_values, target_q2_values)
                target_values = sampled_rewards + self._discount * sampled_dones.logical_not() * target_q_values

            # compute critic loss
            critic_1_values = self.critic_1(sampled_states, sampled_actions)
            critic_2_values = self.critic_2(sampled_states, sampled_actions)

            critic_loss = (F.mse_loss(critic_1_values, target_values) + F.mse_loss(critic_2_values, target_values)) / 2

            # optimization step (critic)
            self.critic_optimizer.zero_grad()
            critic_loss.backward()
            if self._grad_norm_clip > 0:
                nn.utils.clip_grad_norm_(itertools.chain(self.critic_1.parameters(), self.critic_2.parameters()),
                                         self._grad_norm_clip)
            self.critic_optimizer.step()

            self._critic_update_times += 1
            if self._critic_update_times % self._policy_update_delay == 0:
                # compute actor (actor) loss
                actions, log_prob = self.actor(sampled_states)
                critic_1_values = self.critic_1(sampled_states, actions)
                critic_2_values = self.critic_2(sampled_states, actions)

                policy_loss = - torch.min(critic_1_values, critic_2_values).mean()

                # optimization step (actor)
                self.actor_optimizer.zero_grad()
                policy_loss.backward()
                if self._grad_norm_clip > 0:
                    nn.utils.clip_grad_norm_(self.actor.parameters(), self._grad_norm_clip)
                self.actor_optimizer.step()

                # update target networks
                self.target_actor.update_parameters(self.actor, polyak=self._polyak)
                self.target_critic_1.update_parameters(self.critic_1, polyak=self._polyak)
                self.target_critic_2.update_parameters(self.critic_2, polyak=self._polyak)

                self.track_data("Loss / Actor loss", policy_loss.item())

            # update learning rate
            if self._lr_scheduler:
                self.actor_scheduler.step()
                self.critic_scheduler.step()

            # record data
            self.track_data("Loss / Critic loss", critic_loss.item())

            self.track_data("Q-network / Q1 (max)", torch.max(critic_1_values).item())
            self.track_data("Q-network / Q1 (min)", torch.min(critic_1_values).item())
            self.track_data("Q-network / Q1 (mean)", torch.mean(critic_1_values).item())

            self.track_data("Q-network / Q2 (max)", torch.max(critic_2_values).item())
            self.track_data("Q-network / Q2 (min)", torch.min(critic_2_values).item())
            self.track_data("Q-network / Q2 (mean)", torch.mean(critic_2_values).item())

            self.track_data("Target / Target (max)", torch.max(target_values).item())
            self.track_data("Target / Target (min)", torch.min(target_values).item())
            self.track_data("Target / Target (mean)", torch.mean(target_values).item())

            if self._lr_scheduler:
                self.track_data("Learning / Actor learning rate", self.actor_scheduler.get_last_lr()[0])
                self.track_data("Learning / Critic learning rate", self.critic_scheduler.get_last_lr()[0])
