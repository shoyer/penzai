# Copyright 2024 The Penzai Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for gradient checkpointing utility."""

from absl.testing import absltest
import chex
import jax
import jax.numpy as jnp
from penzai.experimental.v2 import pz
from penzai.experimental.v2.models import simple_mlp
from penzai.experimental.v2.toolshed import gradient_checkpointing


class GradientCheckpointingTest(absltest.TestCase):

  def test_gradient_checkpointing(self):
    @pz.pytree_dataclass
    class StateIncrementLayer(pz.nn.Layer):
      state: pz.StateVariable[int]

      def __call__(self, x, **_unused_side_inputs):
        self.state.value = self.state.value + 1
        return x

    mlp = simple_mlp.DropoutMLP.from_config(
        name="mlp",
        init_base_rng=jax.random.key(42),
        feature_sizes=[8, 16, 8],
        drop_rate=0.2,
    )
    state_inc = StateIncrementLayer(pz.StateVariable(0, label="counter"))

    # Non-checkpointed
    model = pz.nn.Sequential([mlp, state_inc])
    rstream = pz.RandomStream.from_base_key(jax.random.key(123))
    base_result = model(
        pz.nx.arange("features", 8).astype(jnp.float32),
        random_stream=rstream,
    )
    self.assertEqual(rstream.offset.value, 1)

    # Checkpointed
    ckptd_model = gradient_checkpointing.Checkpointed(model)
    rstream = pz.RandomStream.from_base_key(jax.random.key(123))
    ckptd_result = ckptd_model(
        pz.nx.arange("features", 8).astype(jnp.float32),
        random_stream=rstream,
    )
    chex.assert_trees_all_equal(base_result, ckptd_result)
    self.assertEqual(rstream.offset.value, 1)
    self.assertEqual(state_inc.state.value, 2)
