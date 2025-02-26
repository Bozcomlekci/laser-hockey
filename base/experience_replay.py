import sys
sys.path.insert(0, '.')
sys.path.insert(1, '..')

import numpy as np
from copy import deepcopy
from .segment_tree import SumSegmentTree, MinSegmentTree
from sac.utils import *
import os


class ExperienceReplay:
    """
    The ExperienceReplay class implements a base class for an experience replay buffer.

    Parameters
    ----------
    max_size : int
        The variable specifies maximum number of (s, a, r, new_state, done) tuples in the buffer.
    """

    def __init__(self, max_size=100000):
        self._transitions = np.asarray([])
        self._current_idx = 0
        self.size = 0
        self.max_size = max_size

    @staticmethod
    def clone_buffer(new_buffer, maxsize):
        old_transitions = deepcopy(new_buffer._transitions)
        buffer = UniformExperienceReplay(max_size=maxsize)
        for t in old_transitions:
            buffer.add_transition(t)

        return buffer

    def add_transition(self, transitions_new):
        if self.size == 0:
            blank_buffer = [np.asarray(transitions_new, dtype=object)] * self.max_size
            self._transitions = np.asarray(blank_buffer)

        self._transitions[self._current_idx, :] = np.asarray(transitions_new, dtype=object)
        self.size = min(self.size + 1, self.max_size)
        self._current_idx = (self._current_idx + 1) % self.max_size

    def preload_transitions(self, path):
        for file in os.listdir(path):
            if file.endswith(".npz"):
                fpath = os.path.join(path, file)

                with np.load(fpath, allow_pickle=True) as d:
                    np_data = d['arr_0'].item()

                    if (
                        # Add a fancy condition
                        True
                    ):
                        transitions = recompute_rewards(np_data, 'Dimitrije_Antic_-_SAC_ЈУГО')
                        for t in transitions:
                            tr = (
                                t[0],
                                t[1],
                                float(t[3]),
                                t[2],
                                bool(t[4]),
                            )
                            self.add_transition(tr)

        print(f'Preloaded data... Buffer size {self.size}.')

    def sample(self, batch_size):
        raise NotImplementedError("Implement the sample method")


class UniformExperienceReplay(ExperienceReplay):
    def __init__(self, max_size=100000):
        super(UniformExperienceReplay, self).__init__(max_size)

    def sample(self, batch_size):
        if batch_size > self.size:
            batch_size = self.size

        indices = np.random.choice(self.size, size=batch_size, replace=False)
        return self._transitions[indices, :]


class PrioritizedExperienceReplay(ExperienceReplay):
    def __init__(self, max_size, alpha, beta):
        super(PrioritizedExperienceReplay, self).__init__(max_size)
        self._alpha = alpha
        self._beta = beta
        self._max_priority = 1.0

        st_capacity = 1
        while st_capacity < max_size:
            st_capacity *= 2
        self._st_sum = SumSegmentTree(st_capacity)
        self._st_min = MinSegmentTree(st_capacity)

    def add_transition(self, transitions_new):
        idx = self._current_idx
        super(PrioritizedExperienceReplay, self).add_transition(transitions_new)
        self._st_min[idx] = self._max_priority ** self._alpha
        self._st_sum[idx] = self._max_priority ** self._alpha

    def _sample_proportionally(self, batch_size):
        indices = []
        p_total = self._st_sum.sum(0, self.size - 1)
        every_range_len = p_total / batch_size
        for i in range(batch_size):
            mass = np.random.uniform(0, 1) * every_range_len + i * every_range_len
            idx = self._st_sum.find_prefixsum_idx(mass)
            indices.append(idx)
        return np.array(indices)

    def sample(self, batch_size):
        if batch_size > self.size:
            batch_size = self.size
        indices = self._sample_proportionally(batch_size)
        weights = []

        # obtain the min probability (max weight accordingly) to scale the other weights (for stability)
        p_min = self._st_min.min() / self._st_sum.sum()
        max_weight = (p_min * self.size) ** (-self._beta)

        for idx in indices:
            # compute probability P(i)
            p_sample = self._st_sum[idx] / self._st_sum.sum()
            weight = (p_sample * self.size) ** (-self._beta)
            weights.append(weight / max_weight)

        return np.concatenate([self._transitions[indices, :], np.array(weights).reshape(-1, 1),
                               indices.reshape(-1, 1)], axis=-1)

    def update_priorities(self, indices, priorities):
        for idx, priority in zip(indices, priorities):
            assert priority > 0
            assert 0 <= idx < self.size
            self._st_sum[idx] = priority ** self._alpha
            self._st_min[idx] = priority ** self._alpha

            self._max_priority = max(self._max_priority, priority)

    def update_beta(self, beta):
        self._beta = beta
