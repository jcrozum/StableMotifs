import StableMotifs.Succession as sm_succession
import StableMotifs.Attractor as sm_attractor

import itertools as it
import networkx as nx
import PyBoolNet

class AttractorRepertoire:
    """The class that stores information about attractors. Initialize using
    either from_primes or from_succession_diagram.

    Attributes
    ----------
    succession_diagram : Succession.SuccessionDiagram
        Succession diagram summarizing the stable motif structure of the model.
    attractors : list of Attractor.Attractor
        List of (possible) attractors in the model.
    reduction_attractors : dictionary
        A dictionary with integer keys that correspond to the
        succession_diagram.digraph nodes. The dictionary values are lists of
        Attractor.Attractor objects that correspond to attractors that exist in
        the region of statespace corresponding to the reduced network
        represented by the key in the succession diagram.
    fewest_attractors : int
        A lower bound on the number of attractors in the model.
    most_attractors : int
        An upper bound on the number of attractors in the model.
    primes : PyBoolNet primes dictionary
        The model rules.

    """

    def __init__(self):
        self.succession_diagram = None
        self.attractors = []
        self.reduction_attractors = {}
        self.fewest_attractors = None
        self.most_attractors = None
        self.primes = None

        self.succession_digraph = None
        self.attractor_equivalence_classes = None
        self.relevant_nodes = None

    @classmethod
    def from_primes(cls,primes,max_simulate_size=20,max_stable_motifs=10000):
        """Build the succession diagram and attractor repertoire from PyBoolNet
        formatted update rules rules.

        Parameters
        ----------
        primes : PyBoolNet primes dictionary
            The model rules.
        max_simulate_size : int
            Maximum number of variables for which to brute-force build a state
            transition graph (the default is 20).
        max_stable_motifs : int
            Maximum number of output lines for PyBoolNet to process from the
            AspSolver (the default is 10000).

        Returns
        -------
        AttractorRepertoire
            AttractorRepertoire object for the input primes.

        """
        x = cls()
        x.primes = primes
        x.analyze_system(primes,max_simulate_size=max_simulate_size,max_stable_motifs=max_stable_motifs)
        x.simplify_diagram([], merge_equivalent_reductions = False)
        return x

    @classmethod
    def from_succession_diagram(cls,succession_diagram):
        """Build the succession diagram and attractor repertoire from a
        precomputed succession diagram.

        Parameters
        ----------
        succession_diagram : Succession.SuccessionDiagram
            Succession diagram summarizing the stable motif structure of the model.

        Returns
        -------
        AttractorRepertoire
            AttractorRepertoire object for the input succession diagram.

        """
        x = cls()
        x.succession_diagram = succession_diagram
        x.primes = succession_diagram.unreduced_primes
        x._get_attractors_from_succession_diagram()
        x._count_attractors()
        x.simplify_diagram([], merge_equivalent_reductions = False)
        return x


    def _get_attractors_from_succession_diagram(self):
        """Extract attractors from the succession diagram of the model.

        """
        for ri, reduction in self.succession_diagram.motif_reduction_dict.items():
            if reduction.terminal == "no": continue

            self.reduction_attractors[ri] = []

            duplicate = False # have we added the attractors for this reduciton yet?
            for attractor in self.attractors:
                if attractor.logically_fixed_nodes == reduction.logically_fixed_nodes:
                    duplicate = True
                    attractor.add_reduction(reduction)
                    self.reduction_attractors[ri].append(attractor)

            if duplicate: continue

            for id,att in enumerate(reduction.attractor_dict_list):
                new_attractor = sm_attractor.Attractor(reduction,id)
                self.attractors.append(new_attractor)
                self.reduction_attractors[ri].append(new_attractor)

    def _count_attractors(self):
        """Place upper and lower bounds on the number of attractors.

        """
        self.fewest_attractors = 0
        self.most_attractors = 0
        for attractor in self.attractors:
            if attractor.guaranteed:
                self.fewest_attractors += 1
            # else: self.fewest_attractors += 0

            if attractor.explored:
                self.most_attractors += 1
            else:
                if attractor.representative[0].deletion_no_motif_attractors is not None:
                    self.most_attractors += len(attractor.representative[0].deletion_no_motif_attractors)
                else:
                    # ludicrously conservative upper bound; assumes STG is all 2-cycles
                    self.most_attractors += 2**(attractor.n_unfixed - 1)

    def analyze_system(self,primes,max_simulate_size=20,max_stable_motifs=10000):
        """Build and process the succession diagram for the model.

        Parameters
        ----------
        primes : PyBoolNet primes dictionary
            The model rules.
        max_simulate_size : int
            Maximum number of variables for which to brute-force build a state
            transition graph (the default is 20).
        max_stable_motifs : int
            Maximum number of output lines for PyBoolNet to process from the
            AspSolver (the default is 10000).
        """
        self.succession_diagram = sm_succession.build_succession_diagram(primes,max_simulate_size=max_simulate_size,max_stable_motifs=max_stable_motifs)
        self._get_attractors_from_succession_diagram()
        self._count_attractors()

    def simplify_diagram(self, projection_nodes, merge_equivalent_reductions = True, keep_only_projection_nodes = False, condense_simple_paths = False):
        if not keep_only_projection_nodes:
            keep = set(self.primes.keys()) - set(projection_nodes)
            ignore = set(projection_nodes)
        else:
            keep = set(projection_nodes)
            ignore = set(self.primes.keys()) - set(projection_nodes)

        G = self.succession_diagram.digraph.copy()

        # Merge equivalent nodes
        if merge_equivalent_reductions:
            for u,v in it.combinations(self.succession_diagram.digraph.nodes(),2):
                if u not in G.nodes(): continue # we've already merged u

                ru = self.succession_diagram.motif_reduction_dict[u]
                rv = self.succession_diagram.motif_reduction_dict[v]
                if PyBoolNet.PrimeImplicants.are_equal(ru.reduced_primes,rv.reduced_primes):
                    if all([ru.logically_fixed_nodes[k]==rv.logically_fixed_nodes[k] for k in keep]):
                        G = nx.contracted_nodes(G,u,v,self_loops=False)

        # If a node v has out degree = 1, then merge it into its only child u
        if condense_simple_paths:
            old_N = float('inf')
            while G.number_of_nodes() < old_N:
                old_N = G.number_of_nodes()
                for v in G.nodes():
                    if G.out_degree(v) == 1:
                        u = next(G.successors(v))
                        G = nx.contracted_nodes(G,u,v,self_loops=False)


        self.succession_digraph = G

        self.attractor_equivalence_classes = {}
        for a in self.attractors:
            keys = set()
            for n in self.succession_digraph.nodes():
                if n not in self.reduction_attractors: continue
                for b in self.reduction_attractors[n]:
                    if all([b.attractor_dict[k] == a.attractor_dict[k] for k in keep]):
                        keys.add(n)
                        break

            merged = False
            for c in self.attractor_equivalence_classes.values():
                if c['states'].items() <= a.attractor_dict.items():
                    c['attractors'].append(a)
                    c['reductions'] |= keys
                    merged = True
            if not merged:
                self.attractor_equivalence_classes[len(self.attractor_equivalence_classes)] = {'states':{k:v for k,v in a.attractor_dict.items() if k in keep},'attractors':[a], 'reductions':keys}

        self.relevant_nodes = keep

    def summary(self):
        """Prints a summary of the attractors to standard output.

        """
        if self.fewest_attractors == 0:
            print("Unable to properly count attractors.")
        elif self.fewest_attractors == self.most_attractors:
            if self.fewest_attractors == 1:
                print("There is 1 attractor.")
            else:
                print("There are",self.fewest_attractors,"attractors.")
        else:
            print("There are between",self.fewest_attractors,"and",self.most_attractors,"attractors.")
        for att in self.attractors:
            print(att.attractor_dict)
            print()
