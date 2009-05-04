from Object import Object
from Arborization import Arborization
from Synapse import Synapse
from GapJunction import GapJunction
from Innervation import Innervation
import xml.etree.ElementTree as ElementTree

class Neurite(Object):
    
    def __init__(self, network, root, *args, **keywords):
        Object.__init__(self, network, *args, **keywords)
        self.root = root
        self._neurites = []
        self.arborization = None
        self.synapses = []
        self._gapJunctions = []
        self._innervations = []
        self.pathway = None
        #self.isStretchReceptor ???
    
    
    @classmethod
    def fromXMLElement(cls, network, xmlElement):
        object = super(Neurite, cls).fromXMLElement(network, xmlElement)
        pathwayId = xmlElement.get('pathwayId')
        object.pathway = network.objectWithId(pathwayId)
        if pathwayId is not None and object.pathway is None:
            raise ValueError, gettext('Pathway with id "%s" does not exist') % (pathwayId)
        object._neurites = []
        for neuriteElement in xmlElement.findall('Neurite'):
            neurite = Neurite.fromXMLElement(network, neuriteElement)
            if neurite is None:
                raise ValueError, gettext('Could not create neurite')
            neurite.root = object
            object._neurites.append(neurite)
            network.addObject(neurite)
        object.arborization = None
        object.synapses = []
        object._gapJunctions = []
        object._innervations = []
        return object
    
    
    def toXMLElement(self, parentElement):
        neuriteElement = Object.toXMLElement(self, parentElement)
        if self.pathway is not None:
            neuriteElement.set('pathwayId', str(self.pathway.networkId))
        for neurite in self._neurites:
            neurite.toXMLElement(neuriteElement)
        return neuriteElement
    
    
    def neuron(self):
        parent = self.root
        while isinstance(parent, Neurite):
            parent = parent.root
        return parent
    
    
    def neurites(self, recurse = False):
        neurites = list(self._neurites)
        if recurse:
            for neurite in self._neurites:
                neurites.append(neurite.neurites(True))
        return neurites
    
    
    def arborize(self, region, sendsOutput=None, receivesInput=None):
        self.arborization = Arborization(self, region, sendsOutput, receivesInput)
        region.arborizations.append(self.arborization)
        self.network.addObject(self.arborization)
    
    
    def synapseOn(self, neurite, activation = None):
        synapse = Synapse(self.network, self, [neurite], activation)
        self.synapses.append(synapse)
        neurite.synapses.append(synapse)
        self.network.addObject(synapse)
        return synapse
    
    
    def incomingSynapses(self):
        incomingSynapses = []
        for synapse in self.synapses:
            if synapse.preSynapticNeurite is not self:
                incomingSynapses.append(synapse)
        return incomingSynapses
    
    
    def outgoingSynapses(self):
        outgoingSynapses = []
        for synapse in self.synapses:
            if synapse.preSynapticNeurite is self:
                outgoingSynapses.append(synapse)
        return outgoingSynapses


    def gapJunctionWith(self, neurite):
        gapJunction = GapJunction(self.network, self, neurite)
        self._gapJunctions.append(gapJunction)
        neurite._gapJunctions.append(gapJunction)
        self.network.addObject(gapJunction)
        return gapJunction
    
    
    def gapJunctions(self, recurse=False):
        junctions = []
        junctions.extend(self._gapJunctions)
        if recurse:
            for subNeurite in self._neurites:
                junctions.extend(subNeurite.gapJunctions(True))
        return junctions
    
    
    def setPathway(self, pathway):
        if self.pathway != None:
            self.pathway.neurites.remove(self)
        self.pathway = pathway
        pathway.neurites.append(self)
        
        
    def innervate(self, muscle):
        innervation = Innervation(self.network, self, muscle)
        self._innervations.append(innervation)
        muscle.innervations.append(innervation)
        self.network.addObject(innervation)
        return innervation
    
    
    def innervations(self, recurse=False):
        innervations = []
        innervations.extend(self._innervations)
        if recurse:
            for subNeurite in self._neurites:
                innervations.extend(subNeurite.innervations(True))
        return innervations
    
    
    def inputs(self):
        inputs = Object.inputs(self)
        # TODO: handle receivesInput is None
        if self.arborization is not None and self.arborization.receivesInput:
            inputs.append(self.arborization)
        for synapse in self.incomingSynapses():
            inputs.append(synapse.preSynapticNeurite)
        inputs.extend(self._gapJunctions)
        for neurite in self._neurites:
            inputs.extend(neurite.inputs())
        return inputs
    
    
    def outputs(self):
        outputs = Object.outputs(self)
        # TODO: handle sendsOutput is None
        if self.arborization is not None and self.arborization.sendsOutput:
            outputs.append(self.arborization)
        for synapse in self.outgoingSynapses():
            outputs.extend(synapse.postSynapticNeurites)
        outputs.extend(self._gapJunctions)
        outputs.extend(self._innervations)
        for neurite in self._neurites:
            outputs.extend(neurite.outputs())
        return outputs
