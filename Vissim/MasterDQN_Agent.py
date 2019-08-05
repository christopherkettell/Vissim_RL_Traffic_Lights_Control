from DQNAgents import DQNAgent
from Vissim_env_class import environment
import os 
import pickle
import numpy as np



class MasterDQN_Agent():
	"""
	A Master class agent containing the other agents.

	"""

	def __init__(self, model_name, vissim_working_directory, sim_length, Model_dictionnary, \
				gamma, alpha, agent_type, memory_size, PER_activated, batch_size, copy_weights_frequency, epsilon_sequence, \
				timesteps_per_second = 1, verbose = True):

		# Model information
		self.Model_dictionnary = Model_dictionnary
		self.model_name = model_name
		self.sim_length = sim_length
		self.vissim_working_directory = vissim_working_directory
		self.timesteps_per_second = timesteps_per_second



		# Agent hyperparameters
		self.gamma = gamma
		self.alpha = alpha
		self.agent_type = agent_type
		self.memory_size = memory_size
		self.PER_activated = PER_activated
		self.batch_size = batch_size
		self.copy_weights_frequency = copy_weights_frequency
		self.epsilon_sequence = epsilon_sequence




		# For saving Put here all relevent information
		self.Session_ID = "DQN" 
		


		self.Agents = {}

		for idx, info in Model_dictionnary['junctions'].items():
				acts = info['default_actions']
				if info['controled_by_com'] :
					self.Agents[idx] = DQNAgent(info['state_size'], len(acts),\
						         idx, memory_size, gamma, self.epsilon_sequence[0], self.alpha, self.copy_weights_frequency, self.PER_activated,\
						         DoubleDQN = True if agent_type == ("DDQN" or "DuelingDDQN") else False,\
						         Dueling = False if agent_type == ("DQN" or "DDQN") else True) 
				

	def train(self, number_of_steps):
		self.env = environment(self.model_name, self.vissim_working_directory, self.sim_length, self.Model_dictionnary,\
			timesteps_per_second = self.timesteps_per_second, mode = 'training', delete_results = True, verbose = True)

		start_state = self.env.get_state()
		actions = {}
		for idx, s in start_state.items():
					actions[idx] = int(self.Agents[idx].choose_action(s))

		for i in range(number_of_steps):
			SARSDs = self.env.step_to_next_action(actions)

			actions = dict()
			for idx , sarsd in SARSDs.items():
				s,a,r,ns,d = sarsd
				
				#print(sarsd)
				self.Agents[idx].remember(s,a,r,ns,d)

				# in order to find the next action you need to evaluate the "next_state" because it is the current state of the simulator
				actions[idx] = int(self.Agents[idx].choose_action(ns))
				
				
			# For the saving , monitoring of the agent 
			if self.env.done :
				self.env.reset()
				
				for idx, agent in self.Agents.items():
					agent.learn_batch(self.batch_size, 1)
					#agent.advance


				
				actions = {}
				for idx, s in start_state.items():
					actions[idx] = self.Agents[idx].choose_action(s)

	# Do a run test and save all the metrics
	def test(self):
		pass

	def prepopulate_memory(self):

		# Chech if suitable folder exists
		prepopulation_directory =  os.path.join(self.vissim_working_directory, self.model_name, "Agents_Results", self.Session_ID)
		if not os.path.exists(prepopulation_directory):
			os.makedirs(prepopulation_directory)
		# Chech if suitable file exists
		if self.PER_activated:
			PER_prepopulation_filename =  os.path.join(prepopulation_directory, 'Agent'+ str(0) + '_PERPre_'+ str(self.memory_size) +'.p')
		else:
			PER_prepopulation_filename =  os.path.join(prepopulation_directory,'Agent'+ str(0) + '_Pre_'+ str(self.memory_size) +'.p')

		prepopulation_exists = os.path.isfile(PER_prepopulation_filename)
		# If it does, process it into the memory
		if prepopulation_exists:
			if self.PER_activated:
				print("Previous Experience Found: Loading into agents")
				for idx, agent in self.Agents.items():
					PER_prepopulation_filename = os.path.join(prepopulation_directory, 'Agent'+ str(idx) + '_PERPre_'+ str(self.memory_size) +'.p')
					memory = pickle.load(open(PER_prepopulation_filename, 'rb'))
					for s,a,r,s,d in memory:
						agent.remember(s,a,r,s,d)
					# FCalculate importance sampling weights
					update_priority_weights(agent, self.memory_size)
					# No simulation ran
			else:
				for idx, agent in self.Agents.items():
					PER_prepopulation_filename =  os.path.join(prepopulation_directory, 'Agent'+ str(idx) + '_Pre_'+ str(self.memory_size) +'.p')
					agent.memory = pickle.load(open(PER_prepopulation_filename, 'rb'))
			return

		else :

			# keep the count of the number of transition in each agent memory
			agents_memory = {}
			for idx, agent in self.Agents.items():
				agents_memory[idx] = []

			# 10000 is a random number to have a simulation speed quick enough
			self.env = environment(self.model_name, self.vissim_working_directory, 10000, self.Model_dictionnary,\
				timesteps_per_second = self.timesteps_per_second, mode = 'training', delete_results = True, verbose = True)

			memory_full = False
			# Time counter
			number_of_action_taken = 0

			start_state = self.env.get_state()
			actions = {}
			for idx, s in start_state.items():
						actions[idx] = int(self.Agents[idx].choose_action(s))

			while not memory_full :
				SARSDs = self.env.step_to_next_action(actions)


				if number_of_action_taken % 1000 == 0:
					for idx, memory in  agents_memory.items():
						print("After {} actions taken by the Agents,  Agent {} memory is {} percent full"\
							.format(number_of_action_taken, idx , np.round(100*len(memory)/self.memory_size,2)))

				actions = dict()

				for idx , sarsd in SARSDs.items():
					s,a,r,ns,d = sarsd
					
					#print(sarsd)
					self.Agents[idx].remember(s,a,r,ns,d)

					agents_memory[idx].append([s,a,r,ns,d])
					
					
					# in order to find the next action you need to evaluate the "next_state" because it is the current state of the simulator
					actions[idx] = int(self.Agents[idx].choose_action(ns))

					number_of_action_taken += 1
				

				# check if all the agents have their memory full
				memory_full = True
				for idx, memory in  agents_memory.items():
					if len(memory) < self.memory_size:
						memory_full = False	
					

				# For the saving , monitoring of the agent 
				if self.env.done :
					self.env.reset()
					
					actions = {}
					for idx, s in start_state.items():
						actions[idx] = self.Agents[idx].choose_action(s)
			

			for idx, agent in self.Agents.items():
				if self.PER_activated:
					update_priority_weights(agent, self.memory_size)
					PER_prepopulation_filename =  os.path.join(prepopulation_directory, 'Agent'+ str(idx) + '_PERPre_'+ str(self.memory_size) +'.p') 

					# Dump random transitions into pickle file for later prepopulation of PER
					print("Memory filled. Saving as:" + PER_prepopulation_filename)
					pickle.dump(agents_memory[idx], open(PER_prepopulation_filename, 'wb'))

				else : 

					PER_prepopulation_filename =  os.path.join(prepopulation_directory,'Agent'+ str(idx) + '_Pre_'+ str(self.memory_size) +'.p')
					print("Memory filled. Saving as:" + PER_prepopulation_filename)
					pickle.dump(agents_memory[idx], open(PER_prepopulation_filename, 'wb'))
	         
			



	def save(self):
		for idx, agent in self.Agents.items():
			agent.save_agent(self.vissim_working_directory, self.model_name, self.Session_ID)


	def load(self, best = True):
		for idx, agent in self.Agents.items():
			agent.load_agent(self.vissim_working_directory, self.model_name , self.Session_ID, best = best)




def update_priority_weights(agent, memory_size):
	#absolute_errors = [] 
	# Sample all memory
	tree_idx, minibatch, ISWeights_mb = agent.memory.sample(memory_size)
	
	state, action, reward, next_state = \
	np.concatenate(minibatch[:,0], axis=0 ), minibatch[:,1].astype('int32') ,minibatch[:,2].reshape(len(minibatch),1), np.concatenate( minibatch[:,3] , axis=0 )
	
	
		
	if agent.DoubleDQN:
		next_action = np.argmax(agent.model.predict(next_state), axis=1)
		target = reward + agent.gamma * agent.target_model.predict(next_state)[np.arange(len(state)) , next_action ].reshape(len(state),1)
		
		#print(target.shape)
		
	else:
		# Fixed Q-Target
		target = reward + agent.gamma * np.max(agent.target_model.predict(next_state),axis=1).reshape(len(state),1)
		print(target.shape)

	target_f = agent.model.predict(state)
	absolute_errors = np.abs(target_f[np.arange(len(target_f)),action].reshape(len(state),1)-target)
	
	
	#Update priority sampling weights
	agent.memory.batch_update(tree_idx, absolute_errors)