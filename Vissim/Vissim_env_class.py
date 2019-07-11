import numpy as np
from NParser import NetworkParser
from Vissim_SCU_class import Signal_Control_Unit
import win32com.client
import os



# The environment class , 
class env():

	"""
	-Load the model
		- it need the controller actions to be defined by hand
	-Deploy the SCU
	-
	"""
	def __init__(self, model_name, vissim_working_directory, sim_length, controlers_actions,\
					 timesteps_per_second = 1, mode = 'training', delete_results = True, verbose = True):

		# Model parameters
		self.model_name = model_name
		self.vissim_working_directory = vissim_working_directory
		self.controlers_actions = controlers_actions


		# Simulation parameters
		self.sim_length = sim_length
		self.mode = mode
		self.timesteps_per_second = timesteps_per_second

		# Evaluation parameters
		self.delete_results = delete_results
		self.verbose = verbose


		# ComServerDisp
		self.Vissim, _, _, _ = COMServerDispatch(model_name, vissim_working_directory, self.sim_length,\
												 self.timesteps_per_second, delete_results = self.delete_results, verbose = self.verbose)

		# The parser can be a methode of the environment
		self.npa = NetworkParser(self.Vissim) 

		self.select_mode()

		# Simulate one step and give the control to COM
		for _ in range(self.timesteps_per_second):
			self.Vissim.Simulation.RunSingleStep()

		for SC in self.npa.signal_controllers_ids:
			for group in self.npa.signal_groups[SC]:
				group.SetAttValue('ContrByCOM',1)

		
		# Create a list of SCUs each scu control a signal controller
		# Need to find later a way to give different green / yellow time to each SCUs
		self.SCUs = []
		for i in self.npa.signal_controllers_ids:
			self.SCUs.append(\
					  Signal_Control_Unit(
						 Vissim,\
						 self.npa.signal_controllers[i],\
						 self.Controllers_Actions[i],\
						 Signal_Groups = self.npa.signal_groups[i],\
						 green_time = 5,\
						 redamber_time = 1,\
						 amber_time = 3, \
						 red_time = 1\
						)\
					  )



	# -function to get the SCUs to later deploy agent on them
	def get_SCU(self):
		return(self.SCUs)

	# does a step in the simulator
	# INPUT a dictionary of action
	# return a dictionnary of (state, action, reward, ) the key will be the SCU's key
	def step(self,actions):
		return(actions)

	# # reset the environnement
	# def reset(self):
	# 	## Connecting the COM Server => Open a new Vissim Window:
	# 	# Server should only be dispatched in first run. Otherwise reload model.
	# 	# Setting Working Directory
	# 	for _ in range(5):
	# 		try:
	# 			## Load the Network:
	# 			Filename = os.path.join(self.vissim_working_directory, self.model_name, (self.model_name+'.inpx'))

	# 			self.Vissim.LoadNet(Filename)

	# 			## Setting Simulation End
	# 			self.Vissim.Simulation.SetAttValue('SimPeriod', self.simulation_length)
	# 			## If a fresh start is needed
	# 			if self.delete_results == True:
	# 				# Delete all previous simulation runs first:
	# 				for simRun in self.Vissim.Net.SimulationRuns:
	# 					self.Vissim.Net.SimulationRuns.RemoveSimulationRun(simRun)
	# 				#print ('Results from Previous Simulations: Deleted. Fresh Start Available.')
	# 		except:
	# 			if _ != 4:
	# 				print("Failed load attempt " +str(_+1)+ "/5. Re-attempting.")
	# 			elif _ == 4:
	# 				raise Exception("Failed 5th loading attempt. Please restart program. TERMINATING NOW.")
	# 				quit()
		
	# 	self.select_mode()

	# 	# Simulate one step and give the control to COM
	# 	for _ in range(self.timesteps_per_second):
	# 		self.Vissim.Simulation.RunSingleStep()

	# 	for SC in self.npa.signal_controllers_ids:
	# 		for group in self.npa.signal_groups[SC]:
	# 			group.SetAttValue('ContrByCOM', 1)
		


	# Set mode to training, demo, debugging
	def select_mode(self):
		# Select the mode for the metric collection 

		# In test mode all the data is stored (The simulation will be slow)
		if self.mode == 'test' :
			#This select quickmode and simulation resolution
			self.timesteps_per_second = 10
			self.Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)
			self.Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode", 1)
			self.Vissim.Simulation.SetAttValue('SimRes', self.timesteps_per_second)
			self.Vissim.SuspendUpdateGUI()  
			
			# set the data mesurement
			self.Vissim.Evaluation.SetAttValue('DataCollCollectData', True)
			self.Vissim.Evaluation.SetAttValue('DataCollInterval', 1)
			
			# set the delay mesurement
			self.Vissim.Evaluation.SetAttValue('DelaysCollectData', True)
			self.Vissim.Evaluation.SetAttValue('DelaysInterval', 1)
			
			# set the data mesurement for each link
			self.Vissim.Evaluation.SetAttValue('LinkResCollectData', True)
			self.Vissim.Evaluation.SetAttValue('LinkResInterval', 1)
			
			# set the data mesurement for each node
			self.Vissim.Evaluation.SetAttValue('NodeResCollectData', True)
			self.Vissim.Evaluation.SetAttValue('NodeResInterval', 1)
			
			# set the queues mesurement 
			self.Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
			self.Vissim.Evaluation.SetAttValue('QueuesInterval', 1)
			
			# set the vehicles perf mesurement 
			self.Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', True)
			self.Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 1)
			
			# set the vehicles travel time mesurement 
			self.Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', True)
			self.Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 1)
			
		# In demo mode we only use the queue counter for the moment
		elif self.mode == 'demo' :

			#This select the simulation resolution
			self.timesteps_per_second = 10
			self.Vissim.Simulation.SetAttValue('SimRes', self.timesteps_per_second)
			
			# set the data mesurement
			self.Vissim.Evaluation.SetAttValue('DataCollCollectData', False)
			self.Vissim.Evaluation.SetAttValue('DataCollInterval', 99999)
			
			# set the delay mesurement
			self.Vissim.Evaluation.SetAttValue('DelaysCollectData', False)
			self.Vissim.Evaluation.SetAttValue('DelaysInterval', 99999)
			
			# set the data mesurement for each link
			self.Vissim.Evaluation.SetAttValue('LinkResCollectData', False)
			self.Vissim.Evaluation.SetAttValue('LinkResInterval', 99999)
			
			# set the data mesurement for each node
			self.Vissim.Evaluation.SetAttValue('NodeResCollectData', False)
			self.Vissim.Evaluation.SetAttValue('NodeResInterval', 99999)
			
			
			# set the queues mesurement 
			self.Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
			self.Vissim.Evaluation.SetAttValue('QueuesInterval', 3)
			
			# set the vehicles perf mesurement 
			self.Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', False)
			self.Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 99999)
			
			# set the vehicles travel time mesurement 
			self.Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', False)
			self.Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 99999)
			
		# In demo mode we only use the queue counter and the delay counter for the moment    
		elif self.mode == 'training' :

			#This select quickmode and simulation resolution
			self.timesteps_per_second = 1
			self.Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)
			self.Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode",1)
			self.Vissim.Simulation.SetAttValue('SimRes', self.timesteps_per_second)
			self.Vissim.SuspendUpdateGUI()  


			# set the data mesurement
			self.Vissim.Evaluation.SetAttValue('DataCollCollectData', False)
			self.Vissim.Evaluation.SetAttValue('DataCollInterval', 3)
			
			# set the delay mesurement
			self.Vissim.Evaluation.SetAttValue('DelaysCollectData', False)
			self.Vissim.Evaluation.SetAttValue('DelaysInterval', 99999)
			
			# set the data mesurement for each link
			self.Vissim.Evaluation.SetAttValue('LinkResCollectData', False)
			self.Vissim.Evaluation.SetAttValue('LinkResInterval', 99999)
			
			# set the data mesurement for each node
			self.Vissim.Evaluation.SetAttValue('NodeResCollectData', False)
			self.Vissim.Evaluation.SetAttValue('NodeResInterval', 99999)
			
			
			# set the queues mesurement 
			self.Vissim.Evaluation.SetAttValue('QueuesCollectData', True)
			self.Vissim.Evaluation.SetAttValue('QueuesInterval', 3)
			
			# set the vehicles perf mesurement 
			self.Vissim.Evaluation.SetAttValue('VehNetPerfCollectData', False)
			self.Vissim.Evaluation.SetAttValue('VehNetPerfInterval', 99999)
			
			# set the vehicles travel time mesurement 
			self.Vissim.Evaluation.SetAttValue('VehTravTmsCollectData', False)
			self.Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 99999)








def COMServerDispatch(model_name, vissim_working_directory, sim_length, timesteps_per_second, delete_results = True, verbose = True):
	for _ in range(5):
		try:
			## Connecting the COM Server => Open a new Vissim Window:
			# Server should only be dispatched in first run. Otherwise reload model.
			# Setting Working Directory
			if verbose:
				print ('Working Directory set to: ' + vissim_working_directory)
				# Check Chache
				print ('Generating Cache...')
			
			# Vissim = win32com.client.gencache.EnsureDispatch("Vissim.Vissim") 
			Vissim = win32com.client.dynamic.Dispatch("Vissim.Vissim") 
		
			if verbose:
				print ('Cache generated.\n')
				print ('****************************')
				print ('*   COM Server dispatched  *')
				print ('****************************\n')
			cache_flag = True
			
			## Load the Network:
			Filename = os.path.join(vissim_working_directory, model_name, (model_name+'.inpx'))
			
			if verbose:
				print ('Attempting to load Model File: ' + model_name+'.inpx ...')
			
			if os.path.exists(Filename):
				Vissim.LoadNet(Filename)
			else:
				raise Exception("ERROR: Could not find Model file: {}".format(Filename))
			
			if verbose:
				print ('Load process successful')
		
			## Setting Simulation End
			Vissim.Simulation.SetAttValue('SimPeriod', sim_length)
			
			if verbose:
				print ('Simulation length set to '+str(sim_length) + ' seconds.')
			
			## If a fresh start is needed
			if delete_results == True:
				# Delete all previous simulation runs first:
				for simRun in Vissim.Net.SimulationRuns:
					Vissim.Net.SimulationRuns.RemoveSimulationRun(simRun)
				if verbose:
					print ('Results from Previous Simulations: Deleted. Fresh Start Available.')
		
			#Pre-fetch objects for stability
			Simulation = Vissim.Simulation
			if verbose:
				print ('Fetched and containerized Simulation Object')
			Network = Vissim.Net
		
			if verbose:
				print ('Fetched and containerized Network Object \n')
				print ('*******************************************************')
				print ('*                                                     *')
				print ('*                 SETUP COMPLETE                      *')
				print ('*                                                     *')
				print ('*******************************************************\n')
			else:
				print('Server Dispatched.')
			return(Vissim, Simulation, Network, cache_flag)
		# If loading fails
		except:
			if _ != 4:
				print("Failed load attempt " +str(_+1)+ "/5. Re-attempting.")
			elif _ == 4:
				raise Exception("Failed 5th loading attempt. Please restart program. TERMINATING NOW.")









