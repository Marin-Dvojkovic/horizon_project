import argparse
import os
import re
from operator import contains

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

parser = argparse.ArgumentParser(
    description="Horizon: Scalable Dependency-driven Data Cleaning"
)
parser.add_argument(
    "--dataset_dir",
    type=str,
    default="datasets/beers",
    help="Directory containing clean data and FDs. (default: datasets/beers)",
)
args = parser.parse_args()


# Class representing a functional dependency
class FD:
    # LHS and RHS attributes
    lhs = []
    rhs = ""
    # Regex for reading from csv
    p = re.compile(r"^([\'\"]?)([\w\d_-]+(?:,\s*[\w\d_-]+)*)\1,\s*([\w\d_-]+)$")

    # Constructor
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    # Constructor from a csv line
    @classmethod
    def create_from_line(cls, line):
        m = cls.p.match(line)
        if not m:
            print(f"{line} is not a valid FD.")
            return None
        groups = m.groups()
        return cls(groups[1].split(","), groups[2])

    # Getter for LHS attributes
    def get_lhs_attributes(self):
        return self.lhs

    # Getter for RHS attribute
    def get_rhs_attribute(self):
        return self.rhs


# Variables for using different datasets
lhs_column_name = "from"
rhs_column_name = "to"
output_dir = "output/"

# Global variables for storing FDs
set_of_fds = []
bound_attributes = set()


# Read FDs into data structure
def read_fds(fds_csv_path):
    global set_of_fds
    file = open(fds_csv_path, "r")

    # Iterate over lines and read via regex
    line = file.readline()
    while line:
        line = file.readline()
        new_fd = FD.create_from_line(line)
        # Skip invalid lines
        if not new_fd:
            continue
        set_of_fds.append(new_fd)

    file.close()
    return


# Read FDs into pandas df
def read_data(dir):
    # Data
    clean_data_path = os.path.join(dir, "clean.csv")
    dirty_data_path = os.path.join(dir, "dirty.csv")
    data = pd.read_csv(dirty_data_path)

    # FDs
    fds_csv_path = os.path.join(dir, "fds.csv")
    fds = pd.read_csv(fds_csv_path)
    read_fds(fds_csv_path)

    return data, fds


def determine_boundedness(fds):
    global bound_attributes
    free_attributes = {}
    fds_to_check = []

    # TODO: Doesn't work correctly
    # Iterate over FDs
    for fd in fds:
        rhs = fd.get_rhs_attribute()
        # For all LHS attributes
        for lhs in fd.get_lhs_attributes():
            # If LHS in free attributes:
            if lhs in free_attributes:
                ## If counter of LHS > 1 or RHS in free attributes already: Don't add LHS to bound attributes
                if free_attributes[lhs] > 1 or rhs in free_attributes:
                    continue
                else:
                    fds_to_check.append((lhs, rhs))
                ## Else we don't know yet (could be at the end) (there must exist at least 𝐶 -> LHS or 𝐶 -> RHS)
                ## If we have checked everything and both conditions are not fulfilled, add either 𝐴 or 𝐵 to bound attributes
            else:
                # If LHS not in free attributes: Add LHS attribute to bound attributes
                bound_attributes.add(lhs)
        # Add RHS attribute to free attributes and +1 counter, if in bound attributes remove from bound attributes
        if rhs not in free_attributes:
            free_attributes[rhs] = 0
        free_attributes[rhs] += 1
        if rhs in bound_attributes:
            bound_attributes.remove(rhs)

    # If we have checked everything and both conditions are not fulfilled, add LHS to bound attributes
    for fd in fds_to_check:
        lhs = fd[0]
        if free_attributes[lhs] > 1 or fd[1] in free_attributes:
            continue
        else:
            bound_attributes.add(lhs)


# Build FD graph from pandas df
def build_fd_graph(fds):
    # Ignore multiple LHS attributes for now
    fds_simple = fds[
        ~fds[lhs_column_name].str.contains(",")
    ]  # TODO: Support hyperedges

    # Create graph from pandas df
    G = nx.from_pandas_edgelist(
        df=fds_simple,
        source=lhs_column_name,
        target=rhs_column_name,
        create_using=nx.DiGraph(),
    )

    print(f"FD graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # nx.draw(G, with_labels=True, pos=nx.spectral_layout(G))
    nx.draw(G, with_labels=True, pos=nx.circular_layout(G))

    figure_name = f"fd_graph_{os.path.basename(args.dataset_dir)}.png"
    plt.savefig(os.path.join(output_dir, figure_name))
    plt.clf()

    return G


def find_strongly_connected_components(G):
    # Build condensation graph (SCCG)
    SCCG = nx.condensation(G)  # Builds SCCG with nx.strongly_connected_components(G)
    member_mapping = {
        node_data[0]: node_data[1]["members"] for node_data in SCCG.nodes.data()
    }

    print(
        f"SCC graph has {SCCG.number_of_nodes()} components and {SCCG.number_of_edges()} edges."
    )

    nx.draw(
        SCCG,
        with_labels=True,
        labels=member_mapping,
        pos=nx.circular_layout(SCCG),
    )

    figure_name = f"scc_fd_graph_{os.path.basename(args.dataset_dir)}.png"
    plt.savefig(os.path.join(output_dir, figure_name))

    return SCCG, member_mapping


def sort_fds(SCCG, member_mapping):
    # Perform topological sorting of SCCG
    print(
        f"Ordered SCCs: {[(i, node) for i, node in enumerate(nx.topological_sort(SCCG))]}"
    )

    # TODO: Proper order representation, for each bound attribute
    final_order = []
    for sccg_node in nx.topological_sort(SCCG):
        for attribute in member_mapping[sccg_node]:
            final_order.append(attribute)

    return final_order


def main():
    # Check dataset
    if not os.path.exists(args.dataset_dir):
        raise ValueError(f"Dataset directory {args.dataset_dir} does not exist.")

    # Create output directory
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Read input FDs from file
    data, fds = read_data(args.dataset_dir)
    # Determine attribute boundedness
    determine_boundedness(set_of_fds)
    print(f"Bound attributes: {bound_attributes}")
    # Build FD graph
    G = build_fd_graph(fds)
    # Turn FD graph into SCCG
    SCCG, member_mapping = find_strongly_connected_components(G)
    # Sort functional dependencies
    order = sort_fds(SCCG, member_mapping)
    print(f"Final order: {order}")


if __name__ == "__main__":
    main()
