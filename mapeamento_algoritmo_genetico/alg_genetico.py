import networkx as nx
import random
import json
from time import process_time
from functools import partial
import Pyro4
import concurrent.futures


# Carregando substrato e requisições
G = nx.read_gml("infra.gml", label="id")

with open('vnr.json', 'r') as f:
    vnrs = json.load(f)
    
with open('populacao_inical.json', 'r') as f:
    populacao_inicial = json.load(f)


_, max_cpu = max(G.nodes.data('cpu'), key=lambda t: t[1])
_, _, max_bandwidth = max(G.edges.data('bandwidth'), key=lambda t: t[2])

_, min_cpu = min(G.nodes.data('cpu'), key=lambda t: t[1])
_, _, min_bandwidth = min(G.edges.data('bandwidth'), key=lambda t: t[2])


# Filtrando e ordenando requisições
new_vnrs = list(filter(lambda VNR: VNR['qtd_nos'] < G.number_of_nodes(), vnrs))
new_vnrs = sorted(new_vnrs, key=lambda VNR: VNR['cpu']/max_cpu + VNR['bandwidth']/max_bandwidth)

# Conectando aos containers
servers = []
for i in range(2, 2+5):
    servers.append(Pyro4.core.Proxy(f"PYRO:Server@192.167.1.{i}:9090"))

# Atendendo as requisições
class AlgoritmoGeneticoDistribuido():
    
    def __init__(self, substrato, populacao_inicial, servers):
        self._substrato = substrato
        self._VNR = None
        self._servers = servers
        _, self._max_cpu = max(substrato.nodes.data('cpu'), key=lambda t: t[1])
        _, _, self._max_bandwidth = max(substrato.edges.data('bandwidth'), key=lambda t: t[2])     
        self._populacao_inicial = populacao_inicial
    
    @property
    def VNR(self):
        return self._VNR
    
    @VNR.setter
    def VNR(self, new_VNR):
        self._VNR = new_VNR
        
    @property
    def substrato(self):
        return self._substrato
    
    @substrato.setter
    def substrato(self, new_substrato):
        self._substrato = new_substrato
        
    def atualiza_individuo(self, individuo):
        individuo['cpu'] = min([self.substrato.nodes[no]['cpu'] for no in individuo['nos']]) 
    
        try:
            bandwidths = []

            for no1, no2 in self._VNR['topologia']:
                caminhos = nx.dijkstra_path(self.substrato, individuo['nos'][no1], individuo['nos'][no2])
                bandwidths += [self.substrato.edges[caminhos[i], no]['bandwidth'] for i, no in enumerate(caminhos[1:])]
            
            individuo['bandwidth'] = min(bandwidths)
            individuo['qtd_saltos'] = len(bandwidths)
        except:
            individuo['bandwidth'] = 0
            individuo['qtd_saltos'] = 0
            
        return individuo
    
    def fitness(self, VNR):
        cpu = (VNR['cpu'] - self._VNR['cpu']) / self._max_cpu
        bandwidth = (VNR['bandwidth'] - self._VNR['bandwidth']) / self._max_bandwidth
        saltos = (VNR['qtd_saltos'] - len(self._VNR['topologia'])) / self.substrato.number_of_edges() 
        
        if cpu >= 0 and bandwidth < 0:
            return bandwidth
        elif cpu < 0 and bandwidth >= 0:
            return cpu

        return cpu + bandwidth - saltos

    def calcular_pontuacao(self, populacao):
        return [self.fitness(x) for x in populacao]
    
    def calculo_roleta(self, pontuacoes):
        menor_pontuacao = min(pontuacoes)
        
        pontuacoes_positivadas = list(map(lambda pontuacao: pontuacao-menor_pontuacao, pontuacoes))
        
        maior_pontuacao = max(pontuacoes_positivadas)
        
        pontuacoes_positivadas_reverso = list(map(lambda pontuacao: (maior_pontuacao-pontuacao) * 5, pontuacoes_positivadas))

        roleta = []
        total = sum(pontuacoes_positivadas_reverso)
        for i, valor in enumerate(pontuacoes_positivadas_reverso):
            repeticao = round(abs((total+1)/(valor + 1)))
            
            roleta.extend([i] * repeticao)
      
        return roleta
      
    def melhor_individuo(self, populacao):
            pontuacoes = self.calcular_pontuacao(populacao)
                  
            indice_maior_pontuacao = pontuacoes.index(max(pontuacoes))
            
            return populacao[indice_maior_pontuacao]

    def server_function_fitness(self, ind_server):
        ind, server = ind_server

        return server.fitness(self.substrato.number_of_edges(), ind, self.VNR, self._max_bandwidth, self._max_cpu)

    def server_function_novo_individuo(self, populacao_prob_mutacao_roleta, server):
        populacao, prob_mutacao, roleta = populacao_prob_mutacao_roleta

        filho = server.novo_individuo(self.substrato.number_of_nodes(), populacao, prob_mutacao, roleta, self.VNR)

        return self.atualiza_individuo(filho)
                 
    def fit(self, repeticoes=100, prob_mutacao=0.1, verbose=False):
        populacao = list(map(self.atualiza_individuo, self._populacao_inicial.copy()))
            
        tam_pop = len(populacao) 

        for count in range(repeticoes):            
            if verbose:
                print("Repetição", count)
            
            with concurrent.futures.ThreadPoolExecutor(5) as executor:
                pontuacoes = []
                for i in range(0, tam_pop, 5):
                     pontuacoes.extend(list(executor.map(self.server_function_fitness, zip(populacao[i:i+5], servers))))
 
                indice_maior_pontuacao = pontuacoes.index(max(pontuacoes))
                if verbose:
                    print('MELHOR INDIVIDUO DA EPOCA ', populacao[indice_maior_pontuacao], 'FITNESS: ', pontuacoes[indice_maior_pontuacao])

                roleta = self.calculo_roleta(pontuacoes)
                #number_of_nodes, populacao, prob_mutacao, roleta, VNR
                server_function_novo_individuo_partial = partial(self.server_function_novo_individuo, (populacao, prob_mutacao, roleta))
                filhos = []
                for i in range(0, tam_pop, 5):
                     filhos.extend(list(executor.map(server_function_novo_individuo_partial, servers)))
                filhos[0] = populacao[indice_maior_pontuacao]

            populacao = filhos

        return self.melhor_individuo(populacao), populacao
    
    def mapear_rede_virtual(self, request):
        print('Virtual Network requisitada: ', request, '\n')

        self.VNR = request

        melhor_individuo, populacao = self.fit(repeticoes=30, prob_mutacao=0.2)

        return (melhor_individuo, request)
    
    def rede_virtual_valida(self, melhor_individuo, request):
        if (melhor_individuo['cpu'] >= request['cpu']) and (melhor_individuo['bandwidth'] >= request['bandwidth']):
            for no in melhor_individuo['nos']:
                self.substrato.nodes[no]['cpu'] -= request['cpu']

            for no1, no2 in request['topologia']:
                caminho = nx.dijkstra_path(self.substrato, melhor_individuo['nos'][no1], melhor_individuo['nos'][no2])

                for i, no in enumerate(caminho[1:]):
                    self.substrato.edges[(caminho[i], no)]['bandwidth'] -= request['bandwidth']

            print('Virtual Network mapeada: ', melhor_individuo, 'para a VNR: ', request, '\n')
        else:
            print('Não encontrou uma solução para a VNR ', request, '\n')


alg_genet = AlgoritmoGeneticoDistribuido(G.copy(), populacao_inicial, servers)


t1 = process_time()

for request in new_vnrs:
    melhor_individuo, _ = alg_genet.mapear_rede_virtual(request)
    alg_genet.rede_virtual_valida(melhor_individuo, request)
    
t2 = process_time()

print('Tempo decorrido em segundos: ', t2-t1)

