import torch

from rofunc.learning.RofuncRL.agents.online.td3_agent import TD3Agent
from rofunc.learning.RofuncRL.processors.noises import GaussianNoise
from rofunc.learning.RofuncRL.trainers.base_trainer import BaseTrainer
from rofunc.learning.RofuncRL.utils.memory import RandomMemory


class TD3Trainer(BaseTrainer):
    def __init__(self, cfg, env, device):
        super().__init__(cfg, env, device)
        self.memory = RandomMemory(memory_size=10000, num_envs=self.env.num_envs, device=device, replacement=True)
        self.agent = TD3Agent(cfg, self.env.observation_space, self.env.action_space, self.memory,
                              device, self.exp_dir, self.rofunc_logger)

        self._exploration_noise = GaussianNoise(0, 0.2, device=device)
        self._exploration_initial_scale = self.cfg.Agent.exploration.initial_scale
        self._exploration_final_scale = self.cfg.Agent.exploration.final_scale
        self._exploration_steps = self.cfg.Agent.exploration.steps

        # clip noise bounds
        if self.env.action_space is not None:
            self.clip_actions_min = torch.tensor(self.env.action_space.low, device=self.device)
            self.clip_actions_max = torch.tensor(self.env.action_space.high, device=self.device)

        self.setup_wandb()

    def get_action(self, states):
        actions = super().get_action(states)

        # add exploration noise
        if self._step < self.random_steps and False:
            # sample noises
            noises = self._exploration_noise.sample(actions.shape)

            # define exploration timesteps
            scale = self._exploration_final_scale
            if self._exploration_steps is None:
                self._exploration_steps = self._step

            # apply exploration noise
            if self._step <= self._exploration_steps:
                scale = (1 - self._step / self._exploration_steps) \
                        * (self._exploration_initial_scale - self._exploration_final_scale) \
                        + self._exploration_final_scale
                noises.mul_(scale)

                # modify actions
                actions.add_(noises)
                actions.clamp_(min=self.clip_actions_min, max=self.clip_actions_max)

                # record noises
                self.agent.track_data("Exploration / Exploration noise (max)", torch.max(noises).item())
                self.agent.track_data("Exploration / Exploration noise (min)", torch.min(noises).item())
                self.agent.track_data("Exploration / Exploration noise (mean)", torch.mean(noises).item())

            else:
                # record noises
                self.agent.track_data("Exploration / Exploration noise (max)", 0)
                self.agent.track_data("Exploration / Exploration noise (min)", 0)
                self.agent.track_data("Exploration / Exploration noise (mean)", 0)

        return actions

    def post_interaction(self):
        # Update agent
        if self._step >= self.start_learning_steps:
            self.agent.update_net()
            self._update_times += 1
            self.rofunc_logger.info(f'Update {self._update_times} times.', local_verbose=False)

        super().post_interaction()