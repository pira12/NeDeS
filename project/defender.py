import random
import simpy
from actions_def import Harden_host, Harden_edge
from actions_att import Exploit, PrivilegeEscalation
import globals as glob

# glob_atts_h = [PrivilegeEscalation("att_h1", 1, 10, 0.8, 1, process="p1")]
# glob_atts_e = [Exploit("att_e1", 1, 10, 0.8, service="s1")]

# glob_hard_h = [Harden_host("harden att_h1", 1, 10, "att_h1"), Harden_host("harden att_h2", 1, 10, "att_h2"), Harden_host("harden att_h3", 1, 10, "att_h3")]
# glob_hard_e = [Harden_edge("harden att_e1", 1, 1, "att_e1"), Harden_edge("harden att_e2", 1, 1, "att_e2"), Harden_edge("harden att_e3", 1, 10, "att_e3")]

# first-layer defense
# last-layer defense
# minimum-cost defense en dan ook voor duration I guess... of kan alles tegelijk hmmmm

def log_scores(attackers, defender, network, env):

    max_score, compromised_score = network.calculate_score()
    def_cost = defender.get_score()

    for i, attacker in enumerate(attackers):
        print(f"Attacker {i} has score: {attacker.score}")

    print("Cost of defending actions:", def_cost)
    print("Sum of compromised score:", compromised_score)
    print("Max score:", max_score)

    print("Added costs and comprimised:", def_cost - compromised_score)

    while True:
        max_score, compromised_score = network.calculate_score()
        def_cost = defender.get_score()
        glob.score_logger.info(f"{env.now} Defender compromised cost {compromised_score} actions cost {def_cost}")

        for i, attacker in enumerate(attackers):
            glob.score_logger.info(f"{env.now} Attacker {i} score {attacker.score}")

        yield env.timeout(1)


class Defender:
    def __init__(self, env, network, strategy):
        self.env = env
        self.network = network
        self.strategy = strategy
        self.score = 0
        self.harden_host_allowed = glob.harden_host_allowed.get()
        self.harden_edge_allowed = glob.harden_edge_allowed.get()

        self.failed_att_hosts = [] #hmmmmm, nodig?
        self.failed_att_edges = [] #hmmmmm, nodig?


    def total_score(self):
        """
        Return the score of the defender and the network.
        """
        max_score, compromised_score = self.network.calculate_score()
        cost_actions = self.get_score()

        return cost_actions - compromised_score


    def get_score(self):
        """
        Return the score of the defender.
        """
        return self.score


    def subtract_score(self, numb):
        """
        Subtract a number from the score.
        ----------
        numb: int
        """
        self.score -= numb

    def get_strategy(self):
        """
        Return the strategy of the defender.
        """

        return self.strategy

    def get_failed_att_hosts(self):
        """
        Return the hosts that have been the target of a failed attack.
        """
        return self.failed_att_hosts


    def add_failed_att_hosts(self, host):
        """
        Add a new failed attack on a host.
        ----------
        host: Host
            The host that was target of a new failed attack.
        """
        self.failed_att_hosts.append(host)


    def get_failed_att_edges(self):
        """
        Return the hosts that have been the target of a failed attack.
        """
        return self.failed_att_edges


    def add_failed_att_edges(self, edge):
        """
        Add a new failed attack on a edge.
        ----------
        edge: Edge
            The edge that was target of a new failed attack.
        """
        self.failed_att_edges.append(edge)


    def get_harden_host_allowed(self):
        """
        Return whether hosts can be hardened.
        """
        return self.harden_host_allowed


    def get_harden_edge_allowed(self):
        """
        Return whether edges can be hardened.
        """
        return self.harden_edge_allowed


    def run(self):
        """
        The main process, which the attacker repeats until the simulation
        is terminated.
        random = Randomly harden edges and hosts.
        last_def = Harden first the sensitive hosts against the relevant
                   Privilege Escalations. Then harden the edges towards the
                   sensitive hosts against exploits. Do random hardenings
                   afterwards.
        """

        if self.get_strategy() == "random":
            # while True:
            #     yield self.env.process(self.random_defense())

            while True:
                yield self.env.process(self.random_defense())

        elif self.get_strategy() == "last layer":
            yield self.env.process(self.last_layer_defense())

            while True:
                yield self.env.process(self.random_defense())

        elif self.get_strategy() == "lazy":
            yield self.env.process(self.lazy_defense(1))

        elif self.get_strategy() == "reactive and random":
            yield self.env.process(self.lazy_defense(2))



    def lazy_defense(self, if_noone):
        """
        Only harden the hosts/edges which had a failed attack.
        Also save which hosts/edges have been attacked.
        ----------
        if_noone : int
            What to do when there is no new failed attack
            0: nothing
            1: wait
            2: do a random hardening
            else: nothing
        """

        att_hosts = self.network.get_failed_att_hosts()
        att_edges = self.network.get_failed_att_edges()

        for host in att_hosts:
            self.add_failed_att_hosts(host)

            if self.get_harden_host_allowed():
                yield self.env.process(self.fully_harden_host(host))

        for edge in att_edges:
            self.add_failed_att_edges(edge)
            if self.get_harden_edge_allowed():
                yield self.env.process(self.fully_harden_edge(edge))

        self.network.reset_failed_att_hosts()
        self.network.reset_failed_att_edges()

        # What to do if there was no failed attack.
        if att_hosts == [] and att_edges == []:
            if if_noone == 1:
                yield self.env.timeout(0.5)
            elif if_noone == 2:
                yield self.env.process(self.random_defense())


    def last_layer_defense(self):
        """
        Harden first the sensitive hosts against the relevant
        Privilege Escalations. Then harden the edges towards the
        sensitive hosts against exploits.
        """
        importants = self.network.get_sensitive_hosts2()

        for imp in importants:
            if self.get_harden_host_allowed():
                yield self.env.process(self.fully_harden_host(imp))

        for imp in importants:
            if self.get_harden_edge_allowed():
                incoming = self.network.get_all_edges_to(imp.get_address())

                for income in incoming:
                    yield self.env.process(self.fully_harden_edge(income))


    def fully_harden_host(self, host):
        """
        Use all relevant hardenings on the given host.
        Wait a little bit if there are none to prevent infinite loops
        when everything is already hardened.
        ----------
        host : Host
        """
        useful = self.get_useful_hardenings_host(host)

        for u in useful:
            yield self.env.process(self.harden_host(host, u))

        if useful == []:
            self.env.timeout(0.1)


    def get_useful_hardenings_host(self, host):
        """
        Determine and return which hardenings are useful.
        This is done by looking which attacks can be performed
        on this host. Hardenings that target those attacks are
        the useful hardenings.
        ----------
        host : Host
        """
        attack_names = host.possible_attacks_names()

        useful_harden = []
        for possible_harden in glob.hard_h:
            if possible_harden.get_attack_type() in attack_names:
                useful_harden.append(possible_harden)

        return useful_harden


    def fully_harden_edge(self, edge):
        """
        Use all relevant hardenings on the given edge.
        Wait a little bit if there are none to prevent infinite loops
        when everything is already hardened.
        ----------
        edge : Edge
        """
        useful = self.get_useful_hardenings_edge(edge)

        for u in useful:
            yield self.env.process(self.harden_edge(edge, u))

        if useful == []:
            self.env.timeout(0.1)


    def get_useful_hardenings_edge(self, edge):
        """
        Determine and return which hardenings are useful.
        This is done by looking which exploits can be performed
        on this edge. Hardenings that target those exploits are
        the useful hardenings.
        ----------
        edge : Edge
        """
        exploit_names = edge.possible_exploits_names()

        useful_harden = []
        for possible_harden in glob.hard_e:
            if possible_harden.get_attack_type() in exploit_names:
                useful_harden.append(possible_harden)

        return useful_harden

    def get_random_def_h(self):
        return random.choice(glob.hard_h)

    def get_random_def_e(self):
        return random.choice(glob.hard_e)


    def random_defense(self):
        """
        Add a defense to a random host or edge.
        It is assumed that either hosts or edges are allowed
        to be hardened, or both.
        """
        threshold = 0.5
        if not self.get_harden_host_allowed():
            threshold = 1
        elif not self.get_harden_edge_allowed():
            threshold = 0


        if random.random() >= threshold:
            random_host = self.network.get_random_host()
            yield self.env.process(self.fully_harden_host(random_host))

        else:
            random_edge = self.network.get_random_edge()
            yield self.env.process(self.fully_harden_edge(random_edge))


    def double_random_defense(self):
        """
        Add a defense to a random host or edge.
        It is assumed that either hosts or edges are allowed
        to be hardened, or both.
        """
        threshold = 0.5
        if not self.get_harden_host_allowed():
            threshold = 1
        elif not self.get_harden_edge_allowed():
            threshold = 0


        if random.random() >= threshold:
            random_host = self.network.get_random_host()
            yield self.env.process(self.harden_host(random_host, self.get_random_def_h()))

        else:
            random_edge = self.network.get_random_edge()
            yield self.env.process(self.harden_edge(random_edge, self.get_random_def_e()))


    def harden_host(self, target_host, harden_action):
        """
        Harden a host against a certain type of attack.
        ----------
        target_host : Host
        harden_action : Harden_host
        """
        glob.logger.info(f"Start Harden_host on host {target_host.get_address()} at {self.env.now}.")
        yield self.env.timeout(harden_action.get_duration())
        target_host.harden(harden_action.get_attack_type())

        self.subtract_score(harden_action.get_cost())
        glob.logger.info(f"Host {target_host.get_address()} hardened against {harden_action.get_attack_type()} at {self.env.now}.")


    def harden_edge(self, target_edge, harden_action):
        """
        Harden an edge against a certain type of attack.
        ----------
        target_edge : Edge
        harden_action : Harden_edge
        """
        glob.logger.info(f"Start Harden_edge on edge {target_edge.get_both_addr()} at {self.env.now}.")
        yield self.env.timeout(harden_action.get_duration())
        target_edge.harden(harden_action.get_attack_type())

        self.subtract_score(harden_action.get_cost())
        glob.logger.info(f"Edge {target_edge.get_both_addr()} hardened against {harden_action.get_attack_type()} at {self.env.now}.")
