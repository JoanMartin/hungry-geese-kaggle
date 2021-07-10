import base64
import bz2
import pickle

import numpy as np
from kaggle_environments.envs.hungry_geese.hungry_geese import Action, Configuration
from tensorflow.keras.layers import Dense
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import SGD
from tensorflow.keras.regularizers import l1_l2

from encoders.seventeen_plane_encoder import SeventeenPlaneEncoder
from game_state import GameState
from goose import Goose
from neural_network_train.networks import medium_bn_no_padding

np.random.seed(123)

X = np.load('/content/drive/MyDrive/TFM/features.npz', allow_pickle=True)['data']
Y = np.load('/content/drive/MyDrive/TFM/labels.npz', allow_pickle=True)['data']

samples = X.shape[0]

board_rows, board_cols = 7, 11
encoder = SeventeenPlaneEncoder(board_cols, board_rows)

input_channels = encoder.num_planes
input_size = input_channels * board_rows * board_cols
input_shape = (board_rows, board_cols, input_channels)

X = X.reshape((samples, board_rows, board_cols, input_channels))

# Hold back a X% of the data for a test set; train on the other 100% - X%
train_samples = int(0.8 * samples)
X_train, X_test = X[:train_samples], X[train_samples:]
Y_train, Y_test = Y[:train_samples], Y[train_samples:]

network_layers = medium_bn_no_padding.layers(input_shape, num_layers=12)

model = Sequential()
for layer in network_layers:
    model.add(layer)
model.add(Dense(4, activation='softmax', kernel_regularizer=l1_l2(l1=0.0005, l2=0.0005)))
model.summary()

sgd = SGD(learning_rate=0.01, clipvalue=0.5)
model.compile(loss='categorical_crossentropy', optimizer=sgd, metrics=['accuracy'])

model.fit(X_train, Y_train,
          batch_size=256,
          epochs=500,
          verbose=1,
          validation_data=(X_test, Y_test))

score = model.evaluate(X_test, Y_test, verbose=0)
print('Test loss:', score[0])
print('Test accuracy:', score[1])

with open("/content/drive/MyDrive/TFM/model.txt", "wb") as f:
    f.write(base64.b64encode(bz2.compress(pickle.dumps(model.to_json()))))
with open("/content/drive/MyDrive/TFM/weights.txt", "wb") as f:
    f.write(base64.b64encode(bz2.compress(pickle.dumps(model.get_weights()), 1)))

############################
# Model evaluation
############################
configuration = Configuration({"columns": board_cols,
                               "rows": board_rows,
                               "hunger_rate": 40,
                               "min_food": 2,
                               "max_length": 99})
goose_white = Goose(0, [72], Action.NORTH)
goose_blue = Goose(1, [49, 60], Action.NORTH)
goose_green = Goose(2, [18, 7, 8], Action.SOUTH)
goose_red = Goose(3, [11, 22], Action.NORTH)

game_state = GameState([goose_white, goose_blue, goose_green, goose_red],
                       [10, 73],
                       configuration,
                       11)

board_tensor = encoder.encode(game_state, 0)

X = np.array([board_tensor])
X = X.reshape((1, board_rows, board_cols, input_channels))
action_probabilities = model.predict(X)[0]

# Increase the distance between the move likely and least likely moves
action_probabilities = action_probabilities ** 3
eps = 1e-6
# Prevent move probabilities from getting stuck at 0 or 1
action_probabilities = np.clip(action_probabilities, eps, 1 - eps)
# Re-normalize to get another probability distribution.
action_probabilities = action_probabilities / np.sum(action_probabilities)

print(action_probabilities)
print(encoder.decode_action_index(np.argmax(action_probabilities).item()))
