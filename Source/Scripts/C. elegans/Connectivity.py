#  Copyright (c) 2010 Howard Hughes Medical Institute.
#  All rights reserved.
#  Use is subject to Janelia Farm Research Campus Software Copyright 1.1 license terms.
#  http://license.janelia.org/license/jfrc_copyright_1_1.html

"""
This script visualizes the connectivity of the C. elegans nervous system.
"""

display.setViewDimensions(3)
display.setShowNeuronNames(True)
display.setLabelsFloatOnTop(True)   # in case the user switches to 2D

# Load the base network.
if not any(network.neurons()):
    execfile('Neurons.py')

# Remove unconnected muscles that would cause problems with the layout.
for muscle in network.muscles():
    removeMuscle = True
    for innervation in muscle.innervations():
        if any(display.visiblesForObject(innervation)):
            removeMuscle = False 
    if removeMuscle:
        display.removeObject(muscle)

# Set up the visualization

updateProgress('Coloring the network...')

for neuron in network.neurons():
    red = green = blue = 0.5
    if neuron.hasFunction(Neuron.Function.SENSORY):
        red = 1.0
    if neuron.hasFunction(Neuron.Function.INTERNEURON):
        blue = 1.0
    if neuron.hasFunction(Neuron.Function.MOTOR):
        green = 1.0
    display.setVisibleColor(neuron, (red, green, blue))
    display.setLabelColor(neuron, (red * 0.125, green * 0.125, blue * 0.125))
    display.setVisiblePosition(neuron, fixed = True)
    display.setVisibleSize(neuron, (.01, .01, .01))
    display.setVisibleOpacity(neuron, 1.0)

# Make all chemical synapses light gray.
for synapse in network.synapses():
    display.setVisibleColor(synapse, (0.75, 0.75, 0.75))
    display.setVisibleOpacity(synapse, 1.0)

# Make all gap junctions dark green.
for gapJunction in network.gapJunctions():
    display.setVisibleColor(gapJunction, (0.0, 0.75, 0.0))
    display.setVisibleOpacity(gapJunction, 1.0)

# Reset the size and opacity of muscles and innervations in case the centrality script has been run.
for muscle in network.muscles():
    display.setVisibleSize(muscle, (.05, .1, .02))
    display.setVisibleOpacity(innervation, 1.0)
for innervation in network.innervations():
    display.setVisibleOpacity(innervation, 1.0)

# Perform a spectral layout weighted by the 'Count' attribute of the synapses and gap junctions.
updateProgress('Laying out the network...')
def weightByCount(edgeVisible):
    countAttr = edgeVisible.client.getAttribute('Count')
    return 0 if not countAttr else countAttr.value()

display.performLayout(layouts['Spectral'](weightFunction = weightByCount, scaling = (40.0, 12.5, 0.25), autoScale = False))
