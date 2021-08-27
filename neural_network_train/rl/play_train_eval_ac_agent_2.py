import argparse
import datetime
import os
import random
import shutil
import tempfile
import time

import h5py
import numpy as np
from kaggle_environments.envs.hungry_geese.hungry_geese import Configuration

from neural_network_train.rl.ac_agent import load_ac_agent
from neural_network_train.rl.experience import ExperienceCollector, combine_experience, load_experience
from neural_network_train.rl.simulate_game import SimulateGame


def load_agent(filename):
    with h5py.File(filename, 'r') as h5file:
        return load_ac_agent(h5file)


def get_temp_file():
    fd, fname = tempfile.mkstemp(prefix='dlgo-train-')
    os.close(fd)
    return fname


configuration = Configuration({"columns": 11,
                               "rows": 7,
                               "hunger_rate": 40,
                               "min_food": 2,
                               "max_length": 99})

simulate_game = SimulateGame(configuration)


def generate_experience(learning_agent, experience_filename, num_games):
    random.seed(int(time.time()) + os.getpid())
    np.random.seed(int(time.time()) + os.getpid())

    agents = [load_agent(learning_agent)] * 4
    collectors = [ExperienceCollector()] * 4

    for i in range(num_games):
        print('Simulating game %d/%d...' % (i + 1, num_games))
        for idx in range(4):
            collectors[idx].begin_episode()
            agents[idx].set_collector(collectors[idx])

        game_state = simulate_game.simulate(agents)
        winner_index = max(game_state.geese, key=lambda x: x.reward).index

        for index, goose in enumerate(game_state.geese):
            if goose.reward <= 0:
                collectors[index].complete_episode(reward=-1)
            elif goose.reward > 0:
                if goose.index == winner_index:
                    collectors[index].complete_episode(reward=1)
                else:
                    collectors[index].complete_episode(reward=0)

    experience = combine_experience(collectors)
    print('Saving experience buffer to %s\n' % experience_filename)
    with h5py.File(experience_filename, 'w') as experience_out_f:
        experience.serialize(experience_out_f)


def train_on_experience(learning_agent, output_file, experience_file, lr, batch_size):
    learning_agent = load_agent(learning_agent)
    with h5py.File(experience_file, 'r') as expf:
        exp_buffer = load_experience(expf)
    learning_agent.train(exp_buffer, lr=lr, batch_size=batch_size)

    with h5py.File(output_file, 'w') as updated_agent_outf:
        learning_agent.serialize(updated_agent_outf)


def evaluate(learning_agent, reference_agent, num_games):
    random.seed(int(time.time()) + os.getpid())
    np.random.seed(int(time.time()) + os.getpid())

    agents = [load_agent(learning_agent),
              load_agent(reference_agent),
              load_agent(reference_agent),
              load_agent(reference_agent)]

    wins, losses = 0, 0
    for i in range(num_games):
        print('Simulating game %d/%d...' % (i + 1, num_games))
        game_state = simulate_game.simulate(agents)
        winner_index = max(game_state.geese, key=lambda x: x.reward).index
        print(f'Agent {winner_index} wins')

        if winner_index == 0:
            wins += 1
        else:
            losses += 1

        print('Agent record: %d/%d' % (wins, wins + losses))

    print('FINAL RESULTS:')
    print('Learner: %d' % wins)
    print('Reference: %d' % losses)

    return wins


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', required=True)
    parser.add_argument('--games-per-batch', '-g', type=int, default=1000)
    parser.add_argument('--work-dir', '-d')
    parser.add_argument('--lr', type=float, default=0.01)
    parser.add_argument('--bs', type=int, default=512)
    parser.add_argument('--log-file', '-l')

    args = parser.parse_args()

    log_f = open(args.log_file, 'a')
    log_f.write('----------------------\n')
    log_f.write(f'Starting from {args.agent} at {datetime.datetime.now()}\n')

    learning_agent = args.agent
    reference_agent = args.agent
    experience_file = os.path.join(args.work_dir, 'exp_temp.hdf5')
    tmp_agent = os.path.join(args.work_dir, 'agent_temp.hdf5')
    working_agent = os.path.join(args.work_dir, 'agent_cur.hdf5')

    total_games = 0
    while True:
        print('Reference: %s' % (reference_agent,))
        log_f.write('Total games so far %d\n' % (total_games,))

        generate_experience(learning_agent,
                            experience_file,
                            num_games=args.games_per_batch)

        train_on_experience(learning_agent,
                            tmp_agent,
                            experience_file,
                            lr=args.lr,
                            batch_size=args.bs)

        wins = evaluate(learning_agent,
                        reference_agent,
                        num_games=100)

        total_games += args.games_per_batch

        print('Won %d / 100 games (%.3f)' % (wins, float(wins) / 100.0))
        log_f.write('Won %d / 100 games (%.3f)\n' % (wins, float(wins) / 100.0))
        shutil.copy(tmp_agent, working_agent)
        learning_agent = working_agent

        if wins >= 60:
            next_filename = os.path.join(args.work_dir, 'agent_%08d.hdf5' % (total_games,))
            shutil.move(tmp_agent, next_filename)
            reference_agent = next_filename
            log_f.write('New reference is %s\n' % next_filename)
        else:
            print('Keep learning\n')

        log_f.flush()


if __name__ == '__main__':
    main()
