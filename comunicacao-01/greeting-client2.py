#Como obter o URI de um servidor remoto?
#- Cliente
# saved as greeting-client.py
import Pyro4
name = input("What is your name? ").strip()
# use name server object lookup uri shortcut
greeting_maker = Pyro4.Proxy("PYRONAME:example.greeting")    
print(greeting_maker.get_fortune(name))   # call method normally