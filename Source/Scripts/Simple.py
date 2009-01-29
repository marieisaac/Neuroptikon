neuron1 = network.createNeuron(name = 'Neuron 1', neurotransmitter = library.neurotransmitter('GABA'))
neuron2 = network.createNeuron(name = 'Neuron 2')
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

neuron3 = network.createNeuron()
neuron3.gapJunctionWith(neuron1)
neuron3.gapJunctionWith(neuron2)
neuron3.arborize(regionA)
neuron3.arborize(regionB)

neuron4 = network.createNeuron(name = 'Neuron 4', neurotransmitter = library.neurotransmitter('acetylcholine'))
neuron4.arborize(regionA, False, True)
neuron4.arborize(regionB, False, True)
muscleX = network.createMuscle(name = 'Muscle X')
neuron4.innervate(muscleX)

neuron4 = network.createNeuron(name = 'Neuron 4', neurotransmitter = library.neurotransmitter('acetylcholine'))
neuron4.arborize(regionA, False, True)
neuron4.arborize(regionB, False, True)
muscleY = network.createMuscle(name = 'Muscle Y')
neuron4.innervate(muscleY)

display.autoLayout()
