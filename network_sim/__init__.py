"""
Network Simulation module for Member 1.
Includes topology generation, traffic simulation, SNMP agent modeling, and fault injection.
"""
from network_sim.topology import build_topology, calculate_edge_cost
from network_sim.traffic import TrafficSimulator
from network_sim.fault_injector import FaultInjector, inject_fault
from network_sim.snmp_agent import SNMPAgentManager

__all__ = [
    "build_topology",
    "calculate_edge_cost",
    "TrafficSimulator",
    "FaultInjector",
    "inject_fault",
    "SNMPAgentManager",
]
