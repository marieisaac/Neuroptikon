neuron1 = network.createNeuron(name = 'Neuron 1', neurotransmitters = [library.neurotransmitter('GABA')], functions = [NeuralFunction.SENSORY])
neuron2 = network.createNeuron(name = 'Neuron 2', functions = [NeuralFunction.SENSORY])
lightStimulus = network.createStimulus(target = neuron1, modality = library.modality('light'))
smellStimulus = network.createStimulus(target = neuron2, modality = library.modality('odor'))
regionA = network.createRegion(name = 'Region A')
regionB = network.createRegion(name = 'Region B')
pathway = regionA.addPathwayToRegion(regionB)

neuron1.arborize(regionA, True, False)
neuron1.arborize(regionB, True, False)
neuron2.arborize(regionA, True, False)
neuron2.arborize(regionB, True, False)
neuron1.synapseOn(neuron2)

neuron3 = network.createNeuron(functions = [NeuralFunction.INTERNEURON])
neuron3.gapJunctionWith(neuron1)
neuron3.gapJunctionWith(neuron2)
neuron3.arborize(regionA)
neuron3.arborize(regionB)

neuron4 = network.createNeuron(name = 'Neuron 4', neurotransmitters = [library.neurotransmitter('ACh')], functions = [NeuralFunction.MOTOR])
neuron4.arborize(regionA, False, True)
neuron4.arborize(regionB, False, True)
muscleX = network.createMuscle(name = 'Muscle X')
neuron4.innervate(muscleX)

neuron5 = network.createNeuron(name = 'Neuron 5', neurotransmitters = [library.neurotransmitter('ACh')], functions = [NeuralFunction.MOTOR])
neuron5.arborize(regionA, False, True)
neuron5.arborize(regionB, False, True)
muscleY = network.createMuscle(name = 'Muscle Y')
neuron5.innervate(muscleY)

display.performLayout(layouts['ForceDirectedLayout'])
