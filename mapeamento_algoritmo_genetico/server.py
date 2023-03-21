import Pyro4
from socket import *
import networkx as nx
import random
import json
from time import process_time
from functools import partial
import math


@Pyro4.expose
class Server():

    def fitness(self, number_of_edges, individuo, VNR, max_bandwidth, max_cpu):
        cpu = (individuo['cpu'] - VNR['cpu']) / max_cpu
        bandwidth = (individuo['bandwidth'] - VNR['bandwidth']) / max_bandwidth
        saltos = (individuo['qtd_saltos'] - len(VNR['topologia'])) / number_of_edges
        
        if cpu >= 0 and bandwidth < 0:

            return bandwidth
        elif cpu < 0 and bandwidth >= 0:

            return cpu

        return cpu + bandwidth - saltos

    def crossover(self, number_of_nodes, populacao, g1, g2, VNR):
        # {'nos': [109, 105, 66], 'cpu': 0, 'bandwidth': 100, 'qtd_saltos': 5}
        qtd_nos = len(populacao[g1]['nos'])
        
        new_individuo = {'nos': [-1 for _ in range(qtd_nos)]}
        
        metade = int(math.ceil(qtd_nos/2))
        
        indices_dos_nos = list(range(qtd_nos))
        random.shuffle(indices_dos_nos)    
        
        if random.random() < 0.5:
            g1, g2 = g2, g1
        
        g = g1
        for i, indice in enumerate(indices_dos_nos):
            if i == metade:
                g = g2
                
            if populacao[g]['nos'][indice] not in new_individuo['nos']:
                new_individuo['nos'][indice] = populacao[g]['nos'][indice]
            else:
                nos_possiveis = list(set(range(number_of_nodes)).difference(set(new_individuo['nos'])))
                new_individuo['nos'][indice] = random.choice(nos_possiveis)

        return new_individuo


    def novo_individuo(self, number_of_nodes, populacao, prob_mutacao, roleta, VNR):
        genitor1 = random.choice(roleta)
        genitor2 = random.choice(roleta)
        filho = self.crossover(number_of_nodes, populacao, genitor1, genitor2, VNR)

        if (random.random() < prob_mutacao):
            qtd_nos_individuo = len(filho['nos'])
                    
            indice_no = random.choice(range(qtd_nos_individuo))
                    
            new_nos_possiveis = list(set(range(number_of_nodes)).difference(set(filho['nos'])))
                        
            filho['nos'][indice_no] = random.choice(new_nos_possiveis)
            
        return filho

HOST = gethostname()
print(HOST)

Pyro4.Daemon.serveSimple({
    Server: 'Server',
}, host=HOST, port=9090, ns=False, verbose=True)
