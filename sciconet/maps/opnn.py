from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

import tensorflow as tf

from . import activations
from . import initializers
from . import regularizers
from .. import config
from ..utils import timing


class OpNN(object):
    """Operator neural networks
    """

    def __init__(
        self,
        layer_size_function,
        layer_size_location,
        activation,
        kernel_initializer,
        regularization=None,
    ):
        if layer_size_function[-1] != layer_size_location[-1]:
            raise ValueError(
                "Output sizes of function NN and location NN do not match."
            )

        self.layer_size_func = layer_size_function
        self.layer_size_loc = layer_size_location
        self.activation = activations.get(activation)
        self.kernel_initializer = initializers.get(kernel_initializer)
        self.kernel_initializer_stacked = initializers.get(
            kernel_initializer + "stacked"
        )
        self.regularizer = regularizers.get(regularization)

        self.training = None
        self.dropout = None
        self.data_id = None
        self.X_func = None
        self.X_loc = None
        self.y = None
        self.target = None

        self.build()

    @property
    def inputs(self):
        return [self.X_func, self.X_loc]

    @property
    def outputs(self):
        return self.y

    @property
    def targets(self):
        return self.target

    @timing
    def build(self):
        print("Building operator neural network...")
        self.training = tf.placeholder(tf.bool)
        self.dropout = tf.placeholder(tf.bool)
        self.data_id = tf.placeholder(tf.uint8)
        self.X_func = tf.placeholder(config.real(tf), [None, self.layer_size_func[0]])
        self.X_loc = tf.placeholder(config.real(tf), [None, self.layer_size_loc[0]])

        # Function NN
        assert (
            len(self.layer_size_func) == 3
        ), "Only support function neural network of ONE hidden layer."
        y_func = self.stacked_dense(
            self.X_func,
            self.layer_size_func[1],
            self.layer_size_func[-1],
            self.activation,
        )

        W = tf.Variable(
            self.kernel_initializer_stacked(
                [self.layer_size_func[2], self.layer_size_func[1]]
            )
        )
        y_func = tf.einsum("bni,ni->bn", y_func, W)

        # Location NN
        y_loc = self.X_loc
        for i in range(1, len(self.layer_size_loc)):
            y_loc = self.dense(
                y_loc,
                self.layer_size_loc[i],
                activation=self.activation,
                regularizer=self.regularizer,
            )

        # Dot product
        self.y = tf.einsum("bi,bi->b", y_func, y_loc)
        self.y = tf.expand_dims(self.y, axis=1)

        self.target = tf.placeholder(config.real(tf), [None, 1])

    def dense(self, inputs, units, activation=None, use_bias=True, regularizer=None):
        return tf.layers.dense(
            inputs,
            units,
            activation=activation,
            use_bias=use_bias,
            kernel_initializer=self.kernel_initializer,
            kernel_regularizer=regularizer,
        )

    def stacked_dense(self, inputs, units, stack_size, activation=None, use_bias=True):
        """Stacked densely-connected NN layer.

        Input shape:
            if inputs is the NN input:
                2D tensor with shape: `(batch_size, input_dim)`.
            else:
                3D tensor with shape: `(batch_size, stack_size, input_dim)`.
        Output shape:
            3D tensor with shape: `(batch_size, stack_size, units)`.
        """
        shape = inputs.get_shape().as_list()
        input_dim = shape[-1]
        W = tf.Variable(self.kernel_initializer_stacked([stack_size, input_dim, units]))
        outputs = tf.einsum("bi,nij->bnj", inputs, W)
        if use_bias:
            b = tf.Variable(tf.zeros([stack_size, units]))
            outputs += b
        if activation is not None:
            return activation(outputs)
        return outputs
