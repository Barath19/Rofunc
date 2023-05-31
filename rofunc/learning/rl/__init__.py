from __future__ import absolute_import

from rofunc.learning.rl.agents.online import PPOAgent
# from rofunc.learning.rl.agents.offline import CQL
# from rofunc.learning.rl.agents.offline import CRR
from rofunc.learning.rl.agents.offline import DTransAgent

algo_map = {
    # "DQN": DQN,
    "PPO": PPOAgent,
    # "SAC": SAC,
    # "CQL": CQL,
    # "CRR": CRR
    "DT": DTransAgent
}