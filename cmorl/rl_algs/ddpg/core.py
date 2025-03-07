import numpy as np
from keras import Model # type: ignore
from keras.layers import Dense, Input, Rescaling, Activation, Lambda, Dropout, BatchNormalization # type: ignore
from keras.constraints import MaxNorm # type: ignore
from gymnasium import spaces
import keras
import tensorflow as tf

from cmorl.utils.loss_composition import clip_keep_in_range, clip_preserve_grads



def mlp_functional(
    inputs,
    hidden_sizes=[32],
    activation="relu",
    use_bias=True,
    kernel_constraint=None,
    use_dropout=False,
    output_activation="sigmoid",
    seed=42
):
    keras.utils.set_random_seed(seed)
    layer = inputs
    for hidden_size in hidden_sizes[:-1]:
        # glorot_limit = np.sqrt(6 / hidden_size*10.0 + layer.shape[1])*0.02
        layer = Dense(
            units=hidden_size,
            activation=activation,
            kernel_constraint=kernel_constraint,
        )(layer)
        if use_dropout:
            layer = Dropout(0.2)(layer)
    outputs = Dense(
        units=hidden_sizes[-1],
        activation=output_activation,
        name="output",
        use_bias=use_bias,
    )(layer)

    return outputs


def scale_by_space(scale_me, space):  # scale_me: [0,1.0]
    return scale_me * (space.high - space.low) + space.low


def unscale_by_space(unscale_me, space):  # outputs [-0.5, 0.5]
    return (unscale_me - space.low) / (space.high - space.low) - 0.5


"""
Actor-Critics
"""

@keras.saving.register_keras_serializable(package="MyLayers")
class RescalingFixed(Rescaling):
    def __init__(self, scale, offset=0.0, **kwargs):
        if type(scale) is dict:
            scale = np.array(scale['config']['value'])
        if type(offset) is dict:
            offset = np.array(offset['config']['value'])
        super().__init__(scale, offset, **kwargs)


class ClipLayer(Activation):
    def __init__(self, min, max, push_strength, **kwargs):
        self.min = min
        self.max = max
        self.push_strength = push_strength
        if "activation" in kwargs:
            del kwargs["activation"]
        super().__init__(activation=lambda x: tf.sigmoid(x*3.5)*(max-min) + min, **kwargs)

    def get_config(self):
        config = super().get_config()
        config.update({
            "min": self.min,
            "max": self.max,
            "push_strength": self.push_strength
        })
        return config

    @classmethod
    def from_config(cls, config):
        return cls(**config)


class CriticActivation(Activation):
    def __init__(self, **kwargs):
        if "activation" in kwargs:
            del kwargs["activation"]
        # super().__init__(activation=lambda x: tf.tanh(x*3.5)**2.0, **kwargs)
        super().__init__(activation=lambda x: x, **kwargs)

def actor(obs_space: spaces.Box, act_space: spaces.Box, hidden_sizes, obs_normalizer, seed=42, push_strength=1e-3):
    inputs = Input([obs_space.shape[0]])
    normalized_input = RescalingFixed(1./obs_normalizer)(inputs)
    # unscaled = unscale_by_space(inputs, obs_space)
    linear_output = mlp_functional(
        normalized_input,
        hidden_sizes + [act_space.shape[0]],
        use_bias=True,
        output_activation=None,
        kernel_constraint=None,
        activation="relu",
        seed=seed
    )
    # tanhed = Activation("tanh")(linear_output)
    clipped = ClipLayer(-1.0, 1.0, push_strength)(linear_output)
    # clipped = Lambda(lambda x: tf.tanh(x*3.5), output_shape=lambda o:o)(linear_output)
    # scaled = scale_by_space(normed, act_space)
    model = keras.Model(inputs, clipped)
    model.compile()
    return model


def critic(
    obs_space: spaces.Box,
    act_space: spaces.Box,
    hidden_sizes,
    obs_normalizer,
    rwds_dim=1,
    seed=42,
    push_strength=1e-3
):
    concated_normalizer = np.concatenate([obs_normalizer, np.ones(act_space.shape[0])])
    inputs = Input([obs_space.shape[0] + act_space.shape[0]])
    normalized_input = RescalingFixed(1. / concated_normalizer)(inputs)
    outputs = mlp_functional(
        normalized_input, hidden_sizes + [rwds_dim], output_activation=None, kernel_constraint=None, use_dropout=False, seed=seed, activation="relu"
    )

    # # name the layer before sigmoid
    before_clip = RescalingFixed(1.0, 0.0)(outputs)

    normed = CriticActivation()(before_clip)
    model = keras.Model(inputs, normed)
    model.compile()
    return model


def mlp_actor_critic(
    obs_space: spaces.Box,
    act_space: spaces.Box,
    rwds_dim: int,
    obs_normalizer=None,
    actor_hidden_sizes=[32, 32],
    critic_hidden_sizes=[400, 300],
    actor_keep_in_range=1e-3,
    critic_keep_in_range=1e-3,
    seed=42
) -> tuple[Model, Model]:
    if obs_normalizer is None:
        obs_normalizer = np.zeros_like(obs_space.high) + 1.0
    obs_normalizer = np.array(obs_normalizer)
    return (
        actor(obs_space, act_space, actor_hidden_sizes, obs_normalizer, seed=seed, push_strength=actor_keep_in_range),
        critic(obs_space, act_space, critic_hidden_sizes, obs_normalizer, rwds_dim, seed=seed, push_strength=critic_keep_in_range),
    )
