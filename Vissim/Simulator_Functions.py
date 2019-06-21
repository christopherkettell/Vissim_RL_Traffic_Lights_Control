import numpy as np
import os
import pickle
from tensorflow.keras.models import load_model



def get_queue_lengths(Vissim, agent):
	West_Queue  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QLen(Current,Last)')
	South_Queue = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QLen(Current,Last)')
	East_Queue  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QLen(Current,Last)')
	North_Queue = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QLen(Current,Last)')
	Queue_length_list = [West_Queue, South_Queue, East_Queue, North_Queue]
	Queue_length_list = [0 if item is None else item for item in Queue_length_list]
	return(Queue_length_list)

def get_delay_timestep(Vissim):
	delay_this_timestep = Vissim.Net.VehicleNetworkPerformanceMeasurement.AttValue('DelayTot(Current, Last, All)')
	return(0 if delay_this_timestep is None else delay_this_timestep)


# Run a Single Episode for a set simulation length
def run_simulation_episode(Agents, Vissim, state_type, reward_type,\
 state_size, simulation_length, timesteps_per_second, seconds_per_green,\
  seconds_per_yellow, demand_list, demand_change_timesteps, mode, PER_activated, Surtrac = False, AC = False):
	
	
	for time_t in range(simulation_length):

		# Change demand every 450 seconds.
		if time_t % demand_change_timesteps == 0:
			change_demand(Vissim, demand_list, demand_change_timesteps, time_t)

		# Cycle through all agents and update them
		Agents_update(Agents, Vissim, state_type,reward_type, state_size, seconds_per_green, seconds_per_yellow, mode, time_t, Surtrac = Surtrac , AC = AC )
		
           
		# Advance the game to the next second (proportionally to the simulator resolution).
		for _ in range(0, timesteps_per_second):
			Vissim.Simulation.RunSingleStep()

		if mode == "test":
			for agent in Agents:
				agent.queues_over_time.append(get_queue_lengths(Vissim, agent))
				agent.accumulated_delay.append(agent.accumulated_delay[-1]+get_delay_timestep(Vissim))

	for agent in Agents:
		agent.update_counter = 1
		agent.intermediate_phase = False
		agent.action = 0
	# Stop the simulation    
	Vissim.Simulation.Stop()

def Agents_update(Agents, Vissim, state_type, reward_type, state_size, seconds_per_green, seconds_per_yellow, mode, time_t, Surtrac = False, AC = False):
	
	for index, agent in enumerate(Agents):
		# Check if agent needs to update
		if agent.update_counter > 0:
			# If it doesn't, substract 1 timestep from the counter and skip the rest
			agent.update_counter -= 1
			continue

		# Update the agent
		elif agent.update_counter == 0:
			if mode	 == "debug":
				print("Update at time {}".format(time_t))
			# Make sure the agent is not in the middle of a transition
			if agent.intermediate_phase == False:
				# Compute the current State and store it in the agent
				agent.newstate = calculate_state(Vissim, state_type, state_size)
				
				# Reward generated by last Action and store it in the agent
				agent.reward   = calculate_reward(Vissim, reward_type)
				
				if not Surtrac :
				# Commit previous State, previous Action, Reward generated and current State to memory
					agent.remember(agent.state, agent.action, agent.reward, agent.newstate)
					
				agent.episode_reward.append(agent.reward)
										
				#print(agent.newstate)
				# Compute the new Action and store it in the agent
				agent.newaction = agent.choose_action(agent.newstate)
				
				
				# In Demonstration Mode, show the Reward of the last cycle
				if mode == "demo":
					print('Agent Reward in this cycle is : {}'.format(round(agent.reward,2)))

				# If the same Action is chosen
				if agent.newaction == agent.action:
					# Extend Timer (do nothing)
					if Surtrac:
						agent.update_counter += agent.actiontime - 1
					else:
						agent.update_counter += seconds_per_green - 1
				
				# If a different Action is chosen
				elif agent.newaction != agent.action:
					# Transition from green to amber and from red to redamber
					green_red_to_amber(agent, seconds_per_yellow,Surtrac)

			# If the agent is in the middle of a transition
			elif agent.intermediate_phase == True:
				# Transition from amber to red and from redamber to green
				amber_to_green_red(agent, seconds_per_green, Surtrac)

			# Update internal State
			agent.state  = agent.newstate
			# Update internal Action
			agent.action = agent.newaction  
			
			# Training during the episode
			if mode == 'training' and AC :
				agent.trainstep += 1
				if len(agent.memory) == agent.n_step_size and agent.trainstep >= 1:
					agent.learn()
					agent.trainstep = 0				
		# Error protection against negative update counters
		else:
			print("ERROR: Update Counter for agent {} is negative. Please investigate.".format(index))

def green_red_to_amber(agent, seconds_per_yellow,Surtrac=False):
	# Fetch the meaning of the Actions from the compatible Actions in the Agent
	previous_action = agent.compatible_actions[agent.action]
	current_action = agent.compatible_actions[agent.newaction]
	# Check transition vector for the whole intersection (1, 0 or -1)
	agent.transition_vector = np.subtract(previous_action, current_action)

	# Cycle through the groups and start the transition
	for index_group, sig_group in enumerate(agent.signal_groups):
		# If the transition vector is > 0, we are changing from GREEN to RED, so set AMBER
		if agent.transition_vector[index_group] == 1:
			sig_group.SetAttValue("SigState", "AMBER")
		# If the transition vector is < 0, we are changing from RED to GREEN, so set to REDAMBER
		elif agent.transition_vector[index_group] == -1:
			sig_group.SetAttValue("SigState", "REDAMBER")
		# If the transition vector is zero, the phase stays the same
		elif agent.transition_vector[index_group] == 0:
			pass
		else:
			print("ERROR: Incongruent new phase and previous phase. Please review the code.")
			break
	# Extend timer after transition is started
	agent.update_counter += seconds_per_yellow	 - 1
	if Surtrac:
		agent.actiontime += - seconds_per_yellow                        
	# Record that a transition is happening
	agent.intermediate_phase = True

def amber_to_green_red(agent, seconds_per_green,Surtrac=False):
	# Finalize the change
	for index_group, sig_group in enumerate(agent.signal_groups):
		# Use transition vector from previous iteration to finish the change
		if agent.transition_vector[index_group] == 1:
			sig_group.SetAttValue("SigState", "RED")
		elif agent.transition_vector[index_group] == -1:
			sig_group.SetAttValue("SigState", "GREEN")
		elif agent.transition_vector[index_group] == 0:
			pass
		else:
			print("ERROR: Incongruent new phase and previous phase. Please review the code.")
			break
	# Mark the transition as finished
	agent.intermediate_phase = False	
	# Set timer for next update 
	if Surtrac :
		agent.update_counter += agent.actiontime - 1		
	else :
		agent.update_counter += seconds_per_green - 1



# We should script those function later because it is only for the basic intersection here
def calculate_state(Vissim, state_type, state_size):
	if state_type == 'Queues':
    	#Obtain Queue Values (average value over the last period)
		West_Queue  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QLen(Current,Last)')
		South_Queue = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QLen(Current,Last)')
		East_Queue  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QLen(Current,Last)')
		North_Queue = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QLen(Current,Last)')
		state = [West_Queue, South_Queue, East_Queue, North_Queue]
		state = [0. if state is None else state for state in state]
		state = np.reshape(state, [1,state_size])
		return(state)
	elif state_type == 'Delay':
		# Obtain Delay Values (average delay in lane * nr cars in queue)
		West_Delay    = Vissim.Net.DelayMeasurements.ItemByKey(1).AttValue('VehDelay(Current,Last,All)') 
		West_Stopped  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QStops(Current,Last)')
		South_Delay   = Vissim.Net.DelayMeasurements.ItemByKey(2).AttValue('VehDelay(Current,Last,All)') 
		South_Stopped = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QStops(Current,Last)')
		East_Delay    = Vissim.Net.DelayMeasurements.ItemByKey(3).AttValue('VehDelay(Current,Last,All)') 
		East_Stopped  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QStops(Current,Last)')
		North_Delay   = Vissim.Net.DelayMeasurements.ItemByKey(4).AttValue('VehDelay(Current,Last,All)') 
		North_Stopped = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QStops(Current,Last)')

		pre_state = [West_Delay, South_Delay, East_Delay, North_Delay, West_Stopped, South_Stopped, East_Stopped, North_Stopped]
		pre_state = [0. if state is None else state for state in pre_state]
		state = [pre_state[0]*pre_state[4], pre_state[1]*pre_state[5], pre_state[2]*pre_state[6], pre_state[3]*pre_state[7]]
		state = np.reshape(state, [1,state_size])
		return(state)
	
	elif state_type == 'QueuesSig':
    	#Obtain Queue Values (average value over the last period)
		West_Queue  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QLen(Current,Last)')		
		South_Queue = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QLen(Current,Last)')		
		East_Queue  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QLen(Current,Last)')
		North_Queue = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QLen(Current,Last)')
		
		# Obtain the signal state  We only need 2 out of 4 for our basic intersection in fact we only need 1 out of 4
		West_Signal = Vissim.Net.SignalHeads.ItemByKey(1).AttValue('SigState') 
		West_Signal = 0. if West_Signal == 'RED' else 1.
		
		South_Signal = Vissim.Net.SignalHeads.ItemByKey(2).AttValue('SigState') 		
		South_Signal = 0. if South_Signal == 'RED' else 1.
		
		state = [West_Queue, South_Queue, East_Queue, North_Queue, West_Signal, South_Signal]
		state = [0. if state is None else state for state in state]
		state = np.reshape(state, [1,state_size])
		
		
		return(state)
		
	elif state_type == 'QueuesSpeedavrOccuperate':
    	#Obtain Queue Values (average value over the last period)
		West_Queue  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QLen(Current,Last)')
		South_Queue = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QLen(Current,Last)')
		East_Queue  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QLen(Current,Last)')
		North_Queue = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QLen(Current,Last)')
		pass
		
	elif state_type == 'MaxFlow':
		pass
	elif state_type == 'FuelConsumption':
		pass
	elif state_type == 'NOx':
		pass
	elif state_type == "COM":
		pass
# For the moment We only work on a particuliar junction    
	elif state_type == "Clusters":
		return(Vp.Clustering(Vissim))
	# Output : - The clustering : A tuple countaining lists of clusters ordered by their time arrival.






# def calculate_reward(agent, reward_type):
# 	if reward_type == 'Queues':
# 		reward = -np.sum([0 if state is None else state for state in agent.newstate[0]])
# 		#print(reward)
# 	elif reward_type == 'QueuesDiff':
# 		current_queue_sum = np.sum([0 if state is None else state for state in agent.newstate[0]])
# 		previous_queue_sum =  np.sum([0 if state is None else state for state in agent.state[0]])
# 		#print("Previous queue: {}".format(previous_queue_sum))
# 		#print("Current queue:  {}".format(current_queue_sum))
# 		#print("Substracted:    {}".format(revious_queue_sum - current_queue_sum))
# 		reward = previous_queue_sum - current_queue_sum
# 	elif reward_type == "QueuesDiffSC":
# 		current_queue_sum = np.sum([0 if state is None else state for state in agent.newstate[0]])
# 		previous_queue_sum =  np.sum([0 if state is None else state for state in agent.state[0]])
# 		#print("Previous queue: {}".format(previous_queue_sum))
# 		#print("Current queue:  {}".format(current_queue_sum))
# 		#print("Substracted:    {}".format(revious_queue_sum - current_queue_sum))
# 		queue_diff = previous_queue_sum - current_queue_sum
# 		reward = queue_diff * 10 - current_queue_sum
# 	elif reward_type == "QueuesDiffSQ":
# 		current_queue_sum = np.sum([0 if state is None else state for state in agent.newstate[0]])
# 		previous_queue_sum =  np.sum([0 if state is None else state for state in agent.state[0]])
# 		#print("Previous queue: {}".format(previous_queue_sum))
# 		#print("Current queue:  {}".format(current_queue_sum))
# 		#print("Substracted:    {}".format(revious_queue_sum - current_queue_sum))
# 		queue_diff = previous_queue_sum - current_queue_sum
# 		reward = queue_diff * 10000 - np.sum(np.array([0 if state is None else state for state in agent.newstate[0]])**2)
# 	else:
# 		raise Exception("ERROR SELECTING REWARD FUNCTION")
# 	agent.episode_reward.append(reward)
# 	return reward


# The calculate reward is now separate from the agent state (this can cause the simulation to be slower)
def calculate_reward(Vissim, reward_type):
	if reward_type == 'Queues':
    	#Obtain Queue Values (average value over the last period)
		West_Queue  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QLen(Current,Last)')
		South_Queue = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QLen(Current,Last)')
		East_Queue  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QLen(Current,Last)')
		North_Queue = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QLen(Current,Last)')
		state = [West_Queue, South_Queue, East_Queue, North_Queue]
		state = [0. if state is None else state for state in state]
		state = np.reshape(state, [1,len(state)])
		
		
	elif reward_type == 'Delay':
		# Obtain Delay Values (average delay in lane * nr cars in queue)
		West_Delay    = Vissim.Net.DelayMeasurements.ItemByKey(1).AttValue('VehDelay(Current,Last,All)') 
		West_Stopped  = Vissim.Net.QueueCounters.ItemByKey(1).AttValue('QStops(Current,Last)')
		South_Delay   = Vissim.Net.DelayMeasurements.ItemByKey(2).AttValue('VehDelay(Current,Last,All)') 
		South_Stopped = Vissim.Net.QueueCounters.ItemByKey(2).AttValue('QStops(Current,Last)')
		East_Delay    = Vissim.Net.DelayMeasurements.ItemByKey(3).AttValue('VehDelay(Current,Last,All)') 
		East_Stopped  = Vissim.Net.QueueCounters.ItemByKey(3).AttValue('QStops(Current,Last)')
		North_Delay   = Vissim.Net.DelayMeasurements.ItemByKey(4).AttValue('VehDelay(Current,Last,All)') 
		North_Stopped = Vissim.Net.QueueCounters.ItemByKey(4).AttValue('QStops(Current,Last)')

		pre_state = [West_Delay, South_Delay, East_Delay, North_Delay, West_Stopped, South_Stopped, East_Stopped, North_Stopped]
		pre_state = [0 if state is None else state for state in pre_state]
		state = [pre_state[0]*pre_state[4], pre_state[1]*pre_state[5], pre_state[2]*pre_state[6], pre_state[3]*pre_state[7]]
		state = np.reshape(state, [1,len(state)])
		
	elif reward_type == 'MaxFlow':
		pass
	elif reward_type == 'FuelConsumption':
		pass
	elif reward_type == 'NOx':
		pass
	elif reward_type == "COM":
		pass
		
	# For the moment We only work on a particuliar junction    	
	if reward_type == 'Queues':
		reward = -np.sum([0. if state is None else state for state in state[0]])
    	#print(reward)
	if reward_type == 'QueuesDifference':
		current_queue_sum = -np.sum([0. if state is None else state for state in state[0]])
		previous_queue_sum =  -np.sum([0. if state is None else state for state in state[0]])
		reward = previous_queue_sum - current_queue_sum
		
	return reward

def prepopulate_memory(Agents, Vissim, state_type, reward_type, state_size, memory_size, vissim_working_directory, model_name, Session_ID, seconds_per_green, seconds_per_yellow, timesteps_per_second, demand_list, demand_change_timesteps, PER_activated):
	memory = []
	# Chech if suitable folder exists
	prepopulation_directory =  os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID)
	if not os.path.exists(prepopulation_directory):
		os.makedirs(prepopulation_directory)
	# Chech if suitable file exists
	if PER_activated:
		PER_prepopulation_filename =  os.path.join(prepopulation_directory,'PERPre_'+ str(memory_size) +'.p')
	else:
		PER_prepopulation_filename =  os.path.join(prepopulation_directory,'Pre_'+ str(memory_size) +'.p')
	prepopulation_exists = os.path.isfile(PER_prepopulation_filename)
	# If it does, process it into the memory
	if prepopulation_exists:
		if PER_activated:
			print("Previous Experience Found: Loading into agent")
			for agent in Agents:
				memory = pickle.load(open(PER_prepopulation_filename, 'rb'))
				for s,a,r,s_ in memory:
					agent.remember(s,a,r,s_)
				# FCalculate importance sampling weights
				update_priority_weights(agent, memory_size)
				# No simulation ran
		else:
			for agent in Agents:
				agent.memory = pickle.load(open(PER_prepopulation_filename, 'rb'))
		
		runflag = False
		
	# Otherwise generate random data, store it in the agent and generate the file above
	else:
		memory_full = False
		# Time counter
		time_t = 0
		# A simulation execution is necessary
		runflag = True
		while not memory_full:
			# Change demand every 450 seconds.
			if time_t % demand_change_timesteps == 0:
				change_demand(Vissim, demand_list, demand_change_timesteps, time_t)

			if time_t % 1000 == 0:
				print("After {} timesteps, memory is {} percent full".format(time_t, np.round(100*len(memory)/memory_size,2)))
			
			# Check every timestep whether the agents need to be updated
			for index, agent in enumerate(Agents):
				# Check if agent needs to update
				if agent.update_counter > 0:
					# If it doesn't, substract 1 timestep from the counter and skip the rest
					agent.update_counter -= 1
					continue
		
				# Update the agent
				elif agent.update_counter == 0:
					# Make sure the agent is not in the middle of a transition
					if agent.intermediate_phase == False:
						# Compute the current State and store it in the agent
						agent.newstate = calculate_state(Vissim, state_type, state_size)
						# Reward generated by last Action and store it in the agent
						agent.reward   = calculate_reward(Vissim, reward_type)
						# Commit previous State, previous Action, Reward generated and current State to memory
						agent.remember(agent.state, agent.action, agent.reward, agent.newstate)
						memory.append((agent.state, agent.action, agent.reward, agent.newstate))
						# Compute the new Action and store it in the agent
						agent.newaction = agent.choose_action(agent.newstate)
		
						# If the same Action is chosen
						if agent.newaction == agent.action:
							# Extend Timer (do nothing)
							agent.update_counter += seconds_per_green - 1
						
						# If a different Action is chosen
						elif agent.newaction != agent.action:
							# Transition from green to amber and from red to redamber
							green_red_to_amber(agent, seconds_per_yellow)
		
					# If the agent is in the middle of a transition
					elif agent.intermediate_phase == True:
						# Transition from amber to red and from redamber to green
						amber_to_green_red(agent, seconds_per_green)
		
					# Update internal State
					agent.state  = agent.newstate
					# Update internal Action
					agent.action = agent.newaction  
		
				# Error protection against negative update counters
				else:
					print("ERROR: Update Counter for agent {} is negative. Please investigate.".format(index))
			
			if len(memory) == memory_size:
				memory_full = True
			# Advance the game to the next second (proportionally to the simulator resolution).
			for _ in range(0, timesteps_per_second):
				Vissim.Simulation.RunSingleStep()
			time_t += 1

		# Fit once to calculate importance sampling weights
		for agent in Agents:
			update_priority_weights(agent, memory_size)
		# Stop the simulation    
		Vissim.Simulation.Stop() 	         

		# Dump random transitions into pickle file for later prepopulation of PER
		print("Memory filled. Saving as:" + PER_prepopulation_filename)
		pickle.dump(memory, open(PER_prepopulation_filename, 'wb'))
		# Stop the simulation   
		Vissim.Simulation.Stop()
	return(memory, Agents, runflag)

# Average reward across agents after an episode
def average_reward(reward_storage, Agents, episode, episodes):
	average_reward = []
	for agent in Agents:
		average_agent_reward = np.average(agent.episode_reward)
		average_reward.append(average_agent_reward)
	average_reward = np.average(average_reward)
	reward_storage.append(average_reward)
    
	if len(Agents)>1:
			# Print the score and break out of the loop
			print("Episode: {}/{}, Epsilon:{}, Average reward: {}".format(episode+1, episodes, np.round(Agents[0].epsilon,2),np.round(average_reward,2)))
			#print("Prediction for [5000,0,5000,0] is: {}".format(Agents[0].model.predict(np.reshape([5000,0,5000,0], [1,4]))))
			for agent in enumerate(Agents):
				print("Agent {}, Average agent reward: {}".format(agent, average_reward[index]))

	# will have to go back here later to make it work with AC			
	else:
		if Agents[0].type == 'AC':
			print("Episode: {}/{}, Epsilon:{}, Average reward: {}".format(episode+1, episodes, np.round(Agents[0].epsilon,2), np.round(average_reward,2)))
		else :
			print("Episode: {}/{}, Epsilon:{}, Average reward: {}".format(episode+1, episodes, np.round(Agents[0].epsilon,2), np.round(average_reward,2)))
			print("Prediction for [50,0,50,0] is: {}".format(Agents[0].model.predict(np.reshape([50,0,50,0], [1,4])))\
	          	 + ("OK" if Agents[0].model.predict(np.reshape([50,0,50,0], [1,4]))[0][0] < Agents[0].model.predict(np.reshape([50,0,50,0], [1,4]))[0][1]  else "NO"))
			print("Prediction for [0,50,0,50] is: {}".format(Agents[0].model.predict(np.reshape([0,50,0,50], [1,4])))\
	        	 + ("OK" if Agents[0].model.predict(np.reshape([0,50,0,50], [1,4]))[0][0] > Agents[0].model.predict(np.reshape([0,50,0,50], [1,4]))[0][1]  else "NO"))
	   
	return(reward_storage, average_reward)


### The next functions differentiate the type of the agent : if it is a DQN the all model with optimisier is saved, otherwise only the weight of the model is saved
# Reload agents
def load_agents(vissim_working_directory, model_name, Agents, Session_ID, best):
	
	for index, agent in enumerate(Agents):
		if agent.type == 'AC':
			print('Loading Pre-Trained Agent, Architecture and Memory.')
			if best:
				Weights_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'_Weights'+'.h5')
			else :
				Weights_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Weights'+'.h5')

			# this is to build the network (to be corrected) 
			agent.test()

			agent.model.load_weights(Weights_Filename)
		
		else :
			print('Loading Pre-Trained Agent, Architecture, Optimizer and Memory.')
			if best:
				Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'.h5')
			else :
				Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'.h5')
			
			agent.model = load_model(Filename)

		if best:
			Memory_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'_Memory'+'.p')
		else:
			Memory_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Memory'+'.p')
		agent.memory = pickle.load(open(Memory_Filename, 'rb'))
		Training_Progress_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Train'+'.p')
		reward_storage = pickle.load(open(Training_Progress_Filename, 'rb'))
		Loss_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Loss'+'.p')
		agent.Loss = pickle.load(open(Loss_Filename, 'rb'))
		
	print('Items successfully loaded.')
	return(Agents, reward_storage)

# Save agents
def save_agents(vissim_working_directory, model_name, Agents, Session_ID, reward_storage):

	# Chech if suitable folder exists
	folder =  os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID)
	if not os.path.exists(folder):
		os.makedirs(folder)
	for index, agent in enumerate(Agents):

		if agent.type == 'AC':
			Weights_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Weights'+'.h5')
			print('Saving architecture, weights state for agent-{}'.format(index))
			
			# little change to save weight instead of the all agent
			agent.model.save_weights(Weights_Filename)

		else :
			Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'.h5')
			print('Saving architecture, weights and optimizer state for agent-{}'.format(index))
			agent.model.save(Filename)

		Memory_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Memory'+'.p')
		print('Dumping agent-{} memory into pickle file'.format(index))
		pickle.dump(agent.memory, open(Memory_Filename, 'wb'))
		Training_Progress_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Train'+'.p')
		print('Dumping Training Results into pickle file.')
		pickle.dump(reward_storage, open(Training_Progress_Filename, 'wb'))
		Loss_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'Agent'+str(index)+'_Loss'+'.p')
		print('Dumping Loss Results into pickle file.')
		pickle.dump(agent.loss, open(Loss_Filename, 'wb'))

######################################################
##### THIS DOESNT WORK FOR MULTIPLE AGENTS. FIX!!!!
# Save the agent producing best reward
def best_agent(reward_storage, average_reward, best_agent_weights, best_agent_memory, vissim_working_directory, model_name, Agents, Session_ID):

	# Chech if suitable folder exists
	folder =  os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID)
	if not os.path.exists(folder):
		os.makedirs(folder)
	if average_reward == np.max(reward_storage):
		for index, agent in enumerate(Agents):
			best_agent_memory = agent.memory

			if agent.type == 'AC' :
				best_agent_weights = agent.model.get_weights()
				Weights_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'_Weights'+'.h5')
				agent.model.save_weights(Weights_Filename)
			else : 
				best_agent_weights = agent.model
				Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'.h5')
				agent.model.save(Filename)

			Memory_Filename = os.path.join(vissim_working_directory, model_name, "Agents_Results", Session_ID,'BestAgent'+str(index)+'_Memory'+'.p')
			pickle.dump(best_agent_memory, open(Memory_Filename, 'wb'))
			print("New best agent found. Saved in {}".format(Memory_Filename))
	return(best_agent_weights, best_agent_memory)

def update_priority_weights(agent, memory_size):
	#absolute_errors = [] 
	# Sample all memory
	tree_idx, minibatch, ISWeights_mb = agent.memory.sample(memory_size)
	
	
	
	
        # for state, action, reward, next_state in minibatch:
        #     if agent.DoubleDQN:
        #         next_action = np.argmax(agent.model.predict(np.reshape(next_state,(1,agent.state_size))), axis=1)
        #         target = reward + agent.gamma * agent.target_model.predict(np.reshape(next_state,(1,agent.state_size)))[0][next_action][0]
        #     else:
        #         # Fixed Q-Target
        #         target = reward + agent.gamma * np.max(agent.target_model.predict(np.reshape(next_state,(1,agent.state_size))))
        #         # No fixed targets version
        #         #target = reward + self.gamma * np.max(self.model.predict(np.reshape(next_state,(1,self.state_size))))

        #       # This section incorporates the reward into the prediction and calculates the absolute error between old and new
        #     target_f = agent.model.predict(state)
        #     absolute_errors.append(abs(target_f[0][action] - target))
	
	state, action, reward, next_state = np.concatenate(minibatch[:,0], axis=0 ), minibatch[:,1].astype('int32') ,minibatch[:,2].reshape(len(minibatch),1), np.concatenate( minibatch[:,3] , axis=0 )
	
	
		
	if agent.DoubleDQN:
		next_action = np.argmax(agent.model.predict(np.reshape(next_state,(len(state),agent.state_size))), axis=1)
		target = reward + agent.gamma * agent.target_model.predict(np.reshape(next_state,(len(state),agent.state_size)))[np.arange(len(state)) , next_action ].reshape(len(state),1)
		
		#print(target.shape)
		
	else:
		# Fixed Q-Target
		target = reward + agent.gamma * np.max(agent.target_model.predict(np.reshape(next_state,(len(state),agent.state_size))),axis=1).reshape(len(state),1)
		print(target.shape)

	target_f = agent.model.predict(state)
	absolute_errors = np.abs(target_f[np.arange(len(target_f)),action].reshape(len(state),1)-target)
	
	
	#Update priority sampling weights
	agent.memory.batch_update(tree_idx, absolute_errors)

# This function will also need to be updated for larger network
# Change the inpute during training
def change_demand(Vissim, demand_list, demand_change_timesteps, time_t):
	for vehicle_input in range(1,(len(Vissim.Net.VehicleInputs)+1)):
		if vehicle_input % 2 == 0:
			Vissim.Net.VehicleInputs.ItemByKey(vehicle_input).SetAttValue('Volume(1)', demand_list[int(time_t/demand_change_timesteps)%len(demand_list)][1])    
		else:
			Vissim.Net.VehicleInputs.ItemByKey(vehicle_input).SetAttValue('Volume(1)', demand_list[int(time_t/demand_change_timesteps)%len(demand_list)][0])    

# Set Fastest Mode in Simulator
def Set_Quickmode(Vissim, timesteps_per_second):
	# Set speed parameters in Vissim
	Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)
	Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode",1)
	Vissim.Simulation.SetAttValue('SimRes', timesteps_per_second)
	Vissim.SuspendUpdateGUI()  

# Select the mode for the metric collection 
# This function will deprecate the select Set_Quickmode
def Select_Vissim_Mode(Vissim, mode):
    

    # In test mode all the data is stored (The simulation will be slow)
	if mode == 'test' :

        #This select quickmode and simulation resolution
		timesteps_per_second = 10
		Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)
		Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode", 1)
		Vissim.Simulation.SetAttValue('SimRes', timesteps_per_second)
		Vissim.SuspendUpdateGUI()  
        
        # set the data mesurement
		Vissim.Evaluation.SetAttValue('DataCollCollectData', True)
		Vissim.Evaluation.SetAttValue('DataCollInterval', 1)
        
		# set the delay mesurement
		Vissim.Evaluation.SetAttValue('DelaysCollectData', True)
		Vissim.Evaluation.SetAttValue('DelaysInterval', 1)
        
		# set the data mesurement for each link
		Vissim.Evaluation.SetAttValue('LinkResCollectData', True)
		Vissim.Evaluation.SetAttValue('LinkResInterval', 1)
        
		# set the data mesurement for each node
		Vissim.Evaluation.SetAttValue('NodeResCollectData', True)
		Vissim.Evaluation.SetAttValue('NodeResInterval', 1)
        
        # set the queues mesurement 
		Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
		Vissim.Evaluation.SetAttValue('QueuesInterval', 1)
        
        # set the vehicles perf mesurement 
		Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', True)
		Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 1)
        
		# set the vehicles travel time mesurement 
		Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', True)
		Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 1)
        
        
    
    # In demo mode we only use the queue counter for the moment
	elif mode == 'demo' :

        #This select the simulation resolution
		timesteps_per_second = 10
		Vissim.Simulation.SetAttValue('SimRes', timesteps_per_second)
        
		# set the data mesurement
		Vissim.Evaluation.SetAttValue('DataCollCollectData', False)
		Vissim.Evaluation.SetAttValue('DataCollInterval', 99999)
        
        # set the delay mesurement
		Vissim.Evaluation.SetAttValue('DelaysCollectData', False)
		Vissim.Evaluation.SetAttValue('DelaysInterval', 99999)
        
		# set the data mesurement for each link
		Vissim.Evaluation.SetAttValue('LinkResCollectData', False)
		Vissim.Evaluation.SetAttValue('LinkResInterval', 99999)
        
        # set the data mesurement for each node
		Vissim.Evaluation.SetAttValue('NodeResCollectData', False)
		Vissim.Evaluation.SetAttValue('NodeResInterval', 99999)
        
        
		# set the queues mesurement 
		Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
		Vissim.Evaluation.SetAttValue('QueuesInterval', 3)
        
        # set the vehicles perf mesurement 
		Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', False)
		Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 99999)
        
		# set the vehicles travel time mesurement 
		Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', False)
		Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 99999)
        
    
    # In demo mode we only use the queue counter and the delay counter for the moment    
	elif mode == 'training' :

    	#This select quickmode and simulation resolution
		timesteps_per_second = 1
		Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)
		Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode",1)
		Vissim.Simulation.SetAttValue('SimRes', timesteps_per_second)
		Vissim.SuspendUpdateGUI()  


        # set the data mesurement
		Vissim.Evaluation.SetAttValue('DataCollCollectData', False)
		Vissim.Evaluation.SetAttValue('DataCollInterval', 99999)
        
        # set the delay mesurement
		Vissim.Evaluation.SetAttValue('DelaysCollectData', False)
		Vissim.Evaluation.SetAttValue('DelaysInterval', 99999)
        
		# set the data mesurement for each link
		Vissim.Evaluation.SetAttValue('LinkResCollectData', False)
		Vissim.Evaluation.SetAttValue('LinkResInterval', 99999)
        
        # set the data mesurement for each node
		Vissim.Evaluation.SetAttValue('NodeResCollectData', False)
		Vissim.Evaluation.SetAttValue('NodeResInterval', 99999)
        
        
		# set the queues mesurement 
		Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
		Vissim.Evaluation.SetAttValue('QueuesInterval', 3)
        
		# set the vehicles perf mesurement 
		Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', False)
		Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 99999)
        
		# set the vehicles travel time mesurement 
		Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', False)
		Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 99999)
        

        