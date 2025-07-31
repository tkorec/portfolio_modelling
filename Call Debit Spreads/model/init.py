
import numpy as np
from cds_portfolio_mc_simulation import CDSPortfolioMCSimulation
mc_simulation = CDSPortfolioMCSimulation(1)
all_portfolio_simulations = mc_simulation.run_monte_carlo_simulation()
all_portfolio_simulations = [sim[1:] for sim in all_portfolio_simulations]
flat_simulations = np.concatenate(all_portfolio_simulations)
print(flat_simulations)


"""
import multiprocessing


def run_simulation(num_simulations):
    from cds_portfolio_mc_simulation import CDSPortfolioMCSimulation
    mc = CDSPortfolioMCSimulation(num_simulations)
    return mc.run_monte_carlo_simulation()

if __name__ == "__main__":
    # Number of total simulations and how many workers to use
    total_simulations = 1
    workers = multiprocessing.cpu_count()
    simulations_per_worker = total_simulations // workers

    with multiprocessing.Pool(processes=workers) as pool:
        # Launch simulations in parallel
        results = pool.map(run_simulation, [simulations_per_worker] * workers)

    from itertools import chain
    all_portfolio_simulations = list(chain.from_iterable(results))

    print(results)
    """