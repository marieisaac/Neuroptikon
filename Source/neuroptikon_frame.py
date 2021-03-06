#  Copyright (c) 2010 Howard Hughes Medical Institute.
#  All rights reserved.
#  Use is subject to Janelia Farm Research Campus Software Copyright 1.1 license terms.
#  http://license.janelia.org/license/jfrc_copyright_1_1.html

import neuroptikon
import wx, wx.py
from pydispatch import dispatcher
import datetime, os, platform, sys, traceback
try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree
import display.display, display.layout
from network.network import Network
from network.region import Region
from network.neuron import Neuron
from network.muscle import Muscle
from network.stimulus import Stimulus

from search.finder import Finder

if platform.system() == 'Darwin':
    import ctypes
    carbon = ctypes.CDLL('/System/Library/Carbon.framework/Carbon')

class NeuroptikonFrame(wx.Frame):
    def __init__(self, network = None, wxId = wx.ID_ANY, populateDisplay = True):
        if network is None:
            title = Network().name()
        else:
            title = network.name()
        wx.Frame.__init__(self, None, wxId, title, size = (800, 600), style = wx.DEFAULT_FRAME_STYLE | wx.FULL_REPAINT_ON_RESIZE)
        
        self.Bind(wx.EVT_ACTIVATE, self.onActivate)
        self.Bind(wx.EVT_UPDATE_UI, self.onUpdateUI)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        
        self.splitter = wx.SplitterWindow(self, wx.ID_ANY, style = wx.SP_LIVE_UPDATE)
        self.splitter.SetMinimumPaneSize(20)
        
        self._modified = False
        
        self.display = display.display.Display(self.splitter)
        self.display.autoVisualize = populateDisplay
        self.display.setNetwork(network)
        dispatcher.connect(self.networkDidChange, ('set', 'network'), self.display)
        dispatcher.connect(self.networkDidChangeSavePath, ('set', 'savePath'), network)
        dispatcher.connect(self.displayDidChange, dispatcher.Any, self.display)
        
        self._scriptLocals = self.scriptLocals()
        self._console = wx.py.shell.Shell(self.splitter, wx.ID_ANY, locals = self._scriptLocals, introText = gettext('Welcome to Neuroptikon.'))
        self._console.autoCompleteIncludeSingle = False
        self._console.autoCompleteIncludeDouble = False
        self.display.setConsole(self._console)

        self.splitter.SplitHorizontally(self.display, self._console)
        self.splitter.SetSashGravity(1.0)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.splitter, 1, wx.EXPAND)
        self.SetAutoLayout(True)
        self.SetSizer(sizer)
        
        self.finder = None
        
        self._progressNestingLevel = 0
        self._progressDialog = None
        self._progressDisplayTime = None
        self._progressMessage = None
        self._progressFractionComplete = None
        self._progressShouldContinue = True
        self._progressLastUpdate = datetime.datetime.now()
        self._progressUpdateDelta = datetime.timedelta(0, 0, 100000)    # Don't update the GUI more than 10 times a second.
        
        self.layoutClasses = {}
        
        self.SetMenuBar(self.menuBar())
        self.SetToolBar(self.toolBar())
        
        dispatcher.connect(self.onDisplayChangedHighlightOnlyWithinSelection, ('set', 'highlightOnlyWithinSelection'), self.display)
        
        if platform.system() == 'Darwin':
            # Have new windows cascade so they don't sit right on top of each other.
            carbon.RepositionWindow(self.MacGetTopLevelWindowRef(), 0, 4)   # 4 = kWindowCascadeOnMainScreen
        
        self.Show(1)
        self.splitter.SetSashPosition(-100)
    
    
    def _updateTitle(self):
        if self.display.name() != None:
            self.SetTitle(self.display.network.name() + ': ' + self.display.name())
        else:        
            self.SetTitle(self.display.network.name())
    
    
    def networkDidChange(self):
        self._scriptLocals['network'] = self.display.network
    
    
    def networkDidChangeSavePath(self):
        self._updateTitle()
    
    
    def displayDidChange(self, signal = None):
        if isinstance(signal, tuple):
            if signal[0] == 'set':
                self.setModified(True)
                if signal[1] == 'name':
                    self._updateTitle()
    
    
    @classmethod
    def _fromXMLElement(cls, xmlElement, network = None):
        frame = NeuroptikonFrame()
        
        # Restore any console history.
        commandHistoryElement = xmlElement.find('CommandHistory')
        if commandHistoryElement is not None:
            history = []
            for commandElement in commandHistoryElement.findall('Command'):
                history += [commandElement.text]
            frame._console.history = history
        
        # TODO: set frame position and size
        
        # Populate the display (can't use the _fromXMLElement pattern here because it doesn't seem possible to re-parent a wx.GLCanvas.
        displayElement = xmlElement.find('Display')
        if displayElement is None:
            raise ValueError, gettext('Display windows must contain a display')
        frame.display.autoVisualize = False
        frame.display.setNetwork(network)
        if network:
            dispatcher.connect(frame.networkDidChangeSavePath, ('set', 'savePath'), network)
        frame.display._fromXMLElement(displayElement)
        frame.networkDidChangeSavePath()
        frame.setModified(False)
        wx.GetApp().inspector.inspectDisplay(frame.display)
        
        return frame
    
    
    def _toXMLElement(self, parentElement):
        frameElement = ElementTree.SubElement(parentElement, 'DisplayWindow')
        
        # Save the display.
        displayElement = self.display._toXMLElement(frameElement)
        if displayElement is None:
            raise ValueError, gettext('Could not save display')
        
        # Save the console history.
        if len(self._console.history) > 0:
            commandHistoryElement = ElementTree.SubElement(frameElement, 'CommandHistory')
            for command in self._console.history:
                ElementTree.SubElement(commandHistoryElement, 'Command').text = command
                
        # TODO: save frame position and size
        
        return frameElement
    
    
    def _toScriptFile(self, scriptFile, networkScriptRefs, savingNetwork):
        scriptFile.write('\n' + gettext('# Create a display') + '\n\n')

        displayNum = self.display.network.displays.index(self.display)
        if displayNum == 0:
            displayRef = 'display'
        else:
            displayRef = 'display' + str(displayNum)
            scriptFile.write(displayRef + ' = displayNetwork(network)\n')
        
        self.display._toScriptFile(scriptFile, networkScriptRefs, displayRef, savingNetwork)
        
        return displayRef
    
    
    def loadBitmap(self, fileName, size = None):
        image = neuroptikon.loadImage(fileName)
        if image is None or not image.IsOk():
            image = wx.EmptyImage(32, 32)
        if size is not None:
            image.Rescale(size[0], size[1], wx.IMAGE_QUALITY_HIGH)
        elif platform.system() == 'Windows':
            image.Rescale(16, 16, wx.IMAGE_QUALITY_HIGH)
        elif platform.system() == 'Linux':
            image.Rescale(32, 32, wx.IMAGE_QUALITY_HIGH)
        return image.ConvertToBitmap()
    
    
    def menuBar(self):
        menuBar = wx.GetApp().menuBar(self)
        
        # pylint: disable=W0201
        
        editMenu = wx.Menu()
        self.Bind(wx.EVT_MENU, self.onUndo, editMenu.Append(wx.ID_UNDO, gettext('Undo\tCtrl-Z'), gettext('Undo the last action')))
        self.Bind(wx.EVT_MENU, self.onRedo, editMenu.Append(wx.ID_REDO, gettext('Redo\tCtrl-Shift-Z'), gettext('Redo the last action')))
        editMenu.AppendSeparator()
        self.cutMenuItem = editMenu.Append(wx.ID_CUT, gettext('Cut\tCtrl-X'), gettext('Move the selected objects to the clipboard'))
        self.Bind(wx.EVT_MENU, self.onCut, self.cutMenuItem)
        self.copyMenuItem = editMenu.Append(wx.ID_COPY, gettext('Copy\tCtrl-C'), gettext('Copy the selected objects to the clipboard'))
        self.Bind(wx.EVT_MENU, self.onCopy, self.copyMenuItem)
        self.pasteMenuItem = editMenu.Append(wx.ID_PASTE, gettext('Paste\tCtrl-V'), gettext('Paste the contents of the clipboard'))
        self.Bind(wx.EVT_MENU, self.onPaste, self.pasteMenuItem)
        self.Bind(wx.EVT_MENU, self.onSelectAll, editMenu.Append(wx.ID_SELECTALL, gettext('Select All\tCtrl-A'), gettext('Select all objects in the window')))
        self.clearMenuItem = editMenu.Append(wx.ID_CLEAR, gettext('Clear\tCtrl-K'), gettext('Clear the contents of the console'))
        self.Bind(wx.EVT_MENU, self.onClear, self.clearMenuItem)
        editMenu.AppendSeparator()
        self.findMenuItem = editMenu.Append(wx.ID_FIND, gettext('Find\tCtrl-F'), gettext('Find objects in the network'))
        self.Bind(wx.EVT_MENU, self.onFind, self.findMenuItem)
        menuBar.Insert(menuBar.GetMenuCount() - 1, editMenu, gettext('&Edit'))
        
        viewMenu = wx.Menu()
        self.Bind(wx.EVT_MENU, wx.GetApp().onOpenInspector, viewMenu.Append(wx.NewId(), gettext('Open Inspector Window\tCtrl-I'), gettext('Open the inspector window')))
        viewMenu.AppendSeparator()  # -----------------
        self.mouseOverSelectingItem = viewMenu.Append(wx.NewId(), gettext('Use Mouse-Over Highlighting'), gettext('Automatically select the object under the mouse'), True)
        self.Bind(wx.EVT_MENU, self.OnUseMouseOverSelecting, self.mouseOverSelectingItem)
        self.decreaseSelectionHighlightDepthItem = viewMenu.Append(wx.NewId(), gettext('Decrease Selection Highlight Depth\tCtrl-Shift--'), gettext('Highlight objects closer to the selection'), True)
        self.Bind(wx.EVT_MENU, self.onDecreaseSelectionHighlightDepth, self.decreaseSelectionHighlightDepthItem)
        self.increaseSelectionHighlightDepthItem = viewMenu.Append(wx.NewId(), gettext('Increase Selection Highlight Depth\tCtrl-Shift-+'), gettext('Highlight objects farther from the selection'), True)
        self.Bind(wx.EVT_MENU, self.onIncreaseSelectionHighlightDepth, self.increaseSelectionHighlightDepthItem)
        self.highlightOnlyWithinSelectionItem = viewMenu.Append(wx.NewId(), gettext('Highlight Only Within Selection'), gettext('Only highlight connections to other selected objects'), True)
        self.Bind(wx.EVT_MENU, self.onHighlightOnlyWithinSelection, self.highlightOnlyWithinSelectionItem)
        viewMenu.AppendSeparator()  # -----------------
        self.showRegionNamesMenuItem = viewMenu.Append(wx.NewId(), gettext('Show Region Names'), gettext('Show/hide the region names'), True)
        self.Bind(wx.EVT_MENU, self.onShowHideRegionNames, self.showRegionNamesMenuItem)
        self.showNeuronNamesMenuItem = viewMenu.Append(wx.NewId(), gettext('Show Neuron Names'), gettext('Show/hide the neuron names'), True)
        self.Bind(wx.EVT_MENU, self.onShowHideNeuronNames, self.showNeuronNamesMenuItem)
        self.showNeuronNamesOnSelectionMenuItem = viewMenu.Append(wx.NewId(), gettext('Show Neuron Names On Selection'), gettext('Show/hide the neuron names on selection'), True)
        self.Bind(wx.EVT_MENU, self.onShowHideNeuronNamesOnSelection, self.showNeuronNamesOnSelectionMenuItem)
        self.printNeuronNamesOnSelectionMenuItem = viewMenu.Append(wx.NewId(), gettext('Print Neuron Names On Selection'), gettext('Print the neuron names in the console when selected'), True)
        self.Bind(wx.EVT_MENU, self.onPrintHideNeuronNamesOnSelection, self.printNeuronNamesOnSelectionMenuItem)
        self.hideUnselectedNeuronsOnSelectionMenuItem = viewMenu.Append(wx.NewId(), gettext('Hide Unselected Neurons On Selection'), gettext('Hides unselected neurons on selection'), True)
        self.Bind(wx.EVT_MENU, self.onHideUnselectedOnSelection, self.hideUnselectedNeuronsOnSelectionMenuItem)
        self.hideSynapsesOnConnectionsMenuItem = viewMenu.Append(wx.NewId(), gettext('Hides Synapses On Connections'), gettext('Hides synapses on connections'), True)
        self.Bind(wx.EVT_MENU, self.onHideSynapsesOnConnections, self.hideSynapsesOnConnectionsMenuItem)
        self.labelsFloatOnTopMenuItem = viewMenu.Append(wx.NewId(), gettext('Float Labels On Top'), gettext('Always show object labels even when the object is behind another'), True)
        self.Bind(wx.EVT_MENU, self.onSetLabelsFloatOnTop, self.labelsFloatOnTopMenuItem)
        self.showFlowMenuItem = viewMenu.Append(wx.NewId(), gettext('Show Flow of Information'), gettext('Animate the connections between objects'), True)
        self.Bind(wx.EVT_MENU, self.onShowFlow, self.showFlowMenuItem)
        self.useGhostsMenuItem = viewMenu.Append(wx.NewId(), gettext('Use Ghosting'), gettext('Dim objects that are not currently selected'), True)
        self.Bind(wx.EVT_MENU, self.onUseGhosts, self.useGhostsMenuItem)
        viewMenu.AppendSeparator()  # -----------------
        for layoutClass in display.layout.layoutClasses():
            layoutId = wx.NewId()
            self.layoutClasses[layoutId] = layoutClass
            menuItem = viewMenu.Append(layoutId, gettext('%s Layout') % layoutClass.name())
            self.Bind(wx.EVT_MENU, self.display.onLayout, menuItem)
            self.Bind(wx.EVT_UPDATE_UI, self.onUpdateLayoutUI, menuItem)
        self.Bind(wx.EVT_MENU, self.display.onLayout, viewMenu.Append(wx.NewId(), gettext('Repeat Last Layout\tCtrl-L')))
        viewMenu.AppendSeparator()  # -----------------
        self.viewIn2DMenuItem = viewMenu.Append(wx.NewId(), gettext('View in 2D\tCtrl-2'), gettext('Show the objects in the xy, xz or zy plane'), True)
        self.Bind(wx.EVT_MENU, self.display.onViewIn2D, self.viewIn2DMenuItem)
        self.viewIn3DMenuItem = viewMenu.Append(wx.NewId(), gettext('View in 3D\tCtrl-3'), gettext('Show the objects in the three dimensional space'), True)
        self.Bind(wx.EVT_MENU, self.display.onViewIn3D, self.viewIn3DMenuItem)
        self.showCompassMenuItem = viewMenu.Append(wx.NewId(), gettext('Show Compass\tCtrl-4'), gettext('Show a compass indicating the current orientation of the display'), True)
        self.Bind(wx.EVT_MENU, self.onShowCompass, self.showCompassMenuItem)
        viewMenu.AppendSeparator()  # -----------------
        self.resetViewMenuItem = viewMenu.Append(wx.NewId(), gettext('Reset View'), gettext('Return to the default view'))
        self.Bind(wx.EVT_MENU, self.onResetView, self.resetViewMenuItem)
        self.zoomToFitMenuItem = viewMenu.Append(wx.ID_ZOOM_FIT, gettext('Zoom to Fit\tCtrl-0'), gettext('Fit all objects within the display'))
        self.Bind(wx.EVT_MENU, self.onZoomToFit, self.zoomToFitMenuItem)
        self.zoomToSelectionMenuItem = viewMenu.Append(wx.NewId(), gettext('Zoom to Selection\tCtrl-\\'), gettext('Fit all selected objects within the display'))
        self.Bind(wx.EVT_MENU, self.onZoomToSelection, self.zoomToSelectionMenuItem)
        self.zoomInMenuItem = viewMenu.Append(wx.ID_ZOOM_IN, gettext('Zoom In\tCtrl-+'), gettext('Make objects appear larger'))
        self.Bind(wx.EVT_MENU, self.onZoomIn, self.zoomInMenuItem)
        self.zoomOutMenuItem = viewMenu.Append(wx.ID_ZOOM_OUT, gettext('Zoom Out\tCtrl--'), gettext('Make objects appear smaller'))
        self.Bind(wx.EVT_MENU, self.onZoomOut, self.zoomOutMenuItem)
        viewMenu.AppendSeparator()  # -----------------
        self.panMenuItem = viewMenu.Append(wx.NewId(), gettext('Pan\tCtrl-Shift-1'), gettext('Dragging the mouse moves the display side to side'))
        self.Bind(wx.EVT_MENU, self.onPan, self.panMenuItem)
        self.rotateMenuItem = viewMenu.Append(wx.NewId(), gettext('Rotate\tCtrl-Shift-2'), gettext('Dragging the mouse rotates the display'))
        self.Bind(wx.EVT_MENU, self.onRotate, self.rotateMenuItem)
        viewMenu.AppendSeparator()  # -----------------
        self.Bind(wx.EVT_MENU, self.display.onSaveView, viewMenu.Append(wx.NewId(), gettext('Save View as...'), gettext('Save the current view to a file')))
        menuBar.Insert(menuBar.GetMenuCount() - 1, viewMenu, gettext('&View'))
        
        if neuroptikon.enableNetworkMenu:
            networkMenu = wx.Menu()
            self.addRegionMenuItem = networkMenu.Append(wx.NewId(), gettext('Add Region...'), gettext('Add a new region to the network'))
            self.addRegionMenuItem.SetBitmap(self.loadBitmap('Region.png', (16, 16)))
            self.Bind(wx.EVT_MENU, self.onAddRegion, self.addRegionMenuItem)
            self.addNeuronMenuItem = networkMenu.Append(wx.NewId(), gettext('Add Neuron...'), gettext('Add a new neuron to the network'))
            self.addNeuronMenuItem.SetBitmap(self.loadBitmap('Neuron.png', (16, 16)))
            self.Bind(wx.EVT_MENU, self.onAddNeuron, self.addNeuronMenuItem)
            self.addMuscleMenuItem = networkMenu.Append(wx.NewId(), gettext('Add Muscle...'), gettext('Add a new muscle to the network'))
            self.addMuscleMenuItem.SetBitmap(self.loadBitmap('Muscle.png', (16, 16)))
            self.Bind(wx.EVT_MENU, self.onAddMuscle, self.addMuscleMenuItem)
            self.addStimulusMenuItem = networkMenu.Append(wx.NewId(), gettext('Add Stimulus...'), gettext('Add a stimulus to the selected object'))
            self.addStimulusMenuItem.SetBitmap(self.loadBitmap('Stimulus.png', (16, 16)))
            self.Bind(wx.EVT_MENU, self.onAddStimulus, self.addStimulusMenuItem)
            networkMenu.AppendSeparator()  # -----------------
            self.deleteObjectsMenuItem = networkMenu.Append(wx.NewId(), gettext('Delete...\tCtrl-Del'), gettext('Remove the selected objects from the network'))
            self.Bind(wx.EVT_MENU, self.onDeleteObjects, self.deleteObjectsMenuItem)
            menuBar.Insert(menuBar.GetMenuCount() - 1, networkMenu, gettext('&Network'))
        
        # pylint: enable=W0201
        
        return menuBar
    
    
    def toolBar(self):
        toolBar = self.CreateToolBar()
        toolBar.AddCheckLabelTool(self.viewIn2DMenuItem.GetId(), gettext('2D View'), self.loadBitmap("View2D.png"), shortHelp = gettext('View in 2D'))
        self.Bind(wx.EVT_TOOL, self.display.onViewIn2D, id = self.viewIn2DMenuItem.GetId())
        toolBar.AddCheckLabelTool(self.viewIn3DMenuItem.GetId(), gettext('3D View'), self.loadBitmap("View3D.png"), shortHelp = gettext('View in 3D'))
        self.Bind(wx.EVT_TOOL, self.display.onViewIn3D, id = self.viewIn3DMenuItem.GetId())
        toolBar.AddSeparator()
        toolBar.AddLabelTool(self.zoomToFitMenuItem.GetId(), gettext('Zoom To Fit'), self.loadBitmap("ZoomToFit.png"), shortHelp = gettext('Zoom To Fit'))
        toolBar.AddLabelTool(self.zoomToSelectionMenuItem.GetId(), gettext('Zoom To Selection'), self.loadBitmap("ZoomToSelection.png"), shortHelp = gettext('Zoom To Selection'))
        toolBar.AddLabelTool(self.zoomInMenuItem.GetId(), gettext('Zoom In'), self.loadBitmap("ZoomIn.png"), shortHelp = gettext('Zoom In'))
        toolBar.AddLabelTool(self.zoomOutMenuItem.GetId(), gettext('Zoom Out'), self.loadBitmap("ZoomOut.png"), shortHelp = gettext('Zoom out'))
        toolBar.AddSeparator()
        toolBar.AddCheckLabelTool(self.panMenuItem.GetId(), gettext('Pan'), self.loadBitmap("Pan.png"), shortHelp = gettext('Scroll the display'))
        toolBar.AddCheckLabelTool(self.rotateMenuItem.GetId(), gettext('Rotate'), self.loadBitmap("Rotate.png"), shortHelp = gettext('Rotate the display'))
        toolBar.AddSeparator()
        toolBar.AddLabelTool(self.decreaseSelectionHighlightDepthItem.GetId(), gettext('Decrease Highlight Depth'), self.loadBitmap("HighlightDepthDecrease.png"), shortHelp = self.decreaseSelectionHighlightDepthItem.GetHelp())
        toolBar.AddLabelTool(self.increaseSelectionHighlightDepthItem.GetId(), gettext('Increase Highlight Depth'), self.loadBitmap("HighlightDepthIncrease.png"), shortHelp = self.increaseSelectionHighlightDepthItem.GetHelp())
        toolBar.AddCheckLabelTool(self.highlightOnlyWithinSelectionItem.GetId(), gettext('Highlight Only Within Selection'), self.loadBitmap("HighlightOnlyWithinSelectionOff.png"), shortHelp = gettext('Only highlight connections to other selected objects'))
        if neuroptikon.enableNetworkMenu:
            toolBar.AddSeparator()
            toolBar.AddCheckLabelTool(self.addRegionMenuItem.GetId(), gettext('Add Region'), self.loadBitmap("Region.png"))
            toolBar.AddCheckLabelTool(self.addNeuronMenuItem.GetId(), gettext('Add Neuron'), self.loadBitmap("Neuron.png"))
            toolBar.AddCheckLabelTool(self.addMuscleMenuItem.GetId(), gettext('Add Muscle'), self.loadBitmap("Muscle.png"))
            toolBar.AddCheckLabelTool(self.addStimulusMenuItem.GetId(), gettext('Add Stimulus'), self.loadBitmap("Stimulus.png"))
            toolBar.AddSeparator()
            toolBar.AddLabelTool(self.deleteObjectsMenuItem.GetId(), gettext('Delete Objects'), self.loadBitmap("Delete.png"))
        toolBar.Realize()
        return toolBar
    
    
    def onUpdateUI(self, event):
        focusedWindow = self.FindFocus()
        eventId = event.GetId() 
        if eventId == wx.ID_UNDO: 
            event.Enable(focusedWindow == self._console and self._console.CanUndo())
        elif eventId == wx.ID_REDO: 
            event.Enable(focusedWindow == self._console and self._console.CanRedo())
        elif eventId == wx.ID_CUT: 
            event.Enable(focusedWindow == self._console and self._console.CanCut())
        elif eventId == wx.ID_COPY: 
            event.Enable(focusedWindow == self._console and self._console.CanCopy())
        elif eventId == wx.ID_PASTE: 
            event.Enable(focusedWindow == self._console and self._console.CanPaste())
        elif eventId == self.mouseOverSelectingItem.GetId():
            event.Check(self.display.useMouseOverSelecting())
        elif eventId == self.highlightOnlyWithinSelectionItem.GetId():
            event.Check(self.display.highlightOnlyWithinSelection())
        elif eventId == self.showRegionNamesMenuItem.GetId():
            event.Check(self.display.showRegionNames())
        elif eventId == self.showNeuronNamesMenuItem.GetId():
            event.Check(self.display.showNeuronNames())
        elif eventId == self.showNeuronNamesOnSelectionMenuItem.GetId():
            event.Check(self.display.showNeuronNamesOnSelection())
        elif eventId == self.hideUnselectedNeuronsOnSelectionMenuItem.GetId():
            event.Check(self.display.hideUnselectedNeurons())
        elif eventId == self.hideSynapsesOnConnectionsMenuItem.GetId():
            event.Check(self.display.hideSynapsesOnConnections())
        elif eventId == self.printNeuronNamesOnSelectionMenuItem.GetId():
            event.Check(self.display.printNeuronNamesOnSelection())
        elif eventId == self.labelsFloatOnTopMenuItem.GetId():
            event.Check(self.display.labelsFloatOnTop())
        elif eventId == self.decreaseSelectionHighlightDepthItem.GetId():
            event.Enable(self.display.selectionHighlightDepth() > 0)
        elif eventId == self.useGhostsMenuItem.GetId():
            event.Check(self.display.useGhosts())
        elif eventId == self.viewIn2DMenuItem.GetId():
            event.Check(self.display.viewDimensions == 2)
        elif eventId == self.viewIn3DMenuItem.GetId():
            event.Check(self.display.viewDimensions == 3)
        elif eventId == self.showCompassMenuItem.GetId():
            event.Check(self.display.isShowingCompass())
        elif eventId == self.resetViewMenuItem.GetId():
            event.Enable(self.display.viewDimensions == 3)
        elif eventId == self.zoomToFitMenuItem.GetId():
            event.Enable(self.display.viewDimensions == 2)
        elif eventId == self.zoomToSelectionMenuItem.GetId():
            event.Enable(self.display.viewDimensions == 2 and any(self.display.selection()))
        elif eventId == self.zoomOutMenuItem.GetId():
            event.Enable(self.display.viewDimensions == 3 or self.display.orthoZoom > 0)
        elif eventId == self.panMenuItem.GetId():
            canPan = self.display.viewDimensions == 3 or self.display.orthoZoom > 0
            event.Check(canPan and self.display.navigationMode() == display.display.PANNING_MODE)
            event.Enable(canPan)
        elif eventId == self.rotateMenuItem.GetId():
            event.Check(self.display.navigationMode() == display.display.ROTATING_MODE)
            event.Enable(self.display.viewDimensions == 3)
        elif neuroptikon.enableNetworkMenu:
            if eventId == self.addRegionMenuItem.GetId():
                event.Check(self.display.objectClassBeingAdded() == Region)
            elif eventId == self.addNeuronMenuItem.GetId():
                event.Check(self.display.objectClassBeingAdded() == Neuron)
            elif eventId == self.addMuscleMenuItem.GetId():
                event.Check(self.display.objectClassBeingAdded() == Muscle)
            elif eventId == self.addStimulusMenuItem.GetId():
                event.Check(self.display.objectClassBeingAdded() == Stimulus)
            elif eventId == self.deleteObjectsMenuItem.GetId():
                event.Enable(any(self.display.selection()))
    
    
    def onDisplayChangedHighlightOnlyWithinSelection(self):
        if self.display.highlightOnlyWithinSelection():
            bitmap = self.loadBitmap("HighlightOnlyWithinSelectionOn.png")
        else:
            bitmap = self.loadBitmap("HighlightOnlyWithinSelectionOff.png")
        self.GetToolBar().SetToolNormalBitmap(self.highlightOnlyWithinSelectionItem.GetId(), bitmap)
        
    
    def onActivate(self, event):
        wx.GetApp().inspector.inspectDisplay(self.display)
        event.Skip()
    
    
    def scriptLocals(self):
        scriptLocals = neuroptikon.scriptLocals()
        scriptLocals['network'] = self.display.network
        scriptLocals['display'] = self.display
        scriptLocals['updateProgress'] = self.updateProgress
        scriptLocals['showMessage'] = self.showMessage
        if 'DEBUG' in os.environ:
            scriptLocals['profileScript'] = self._profileScript
        return scriptLocals
    
        
    def runScript(self, scriptPath):
        scriptName = os.path.basename(scriptPath)
        
        self.beginProgress(gettext('Running %s...') % (scriptName))
        
        if 'DEBUG' in os.environ:
            startTime = datetime.datetime.now()
        
        refreshWasSuppressed = self.display._suppressRefresh
        self.display._suppressRefresh = True
        self.Freeze()
        
        prevDir = os.getcwd()
        os.chdir(os.path.dirname(scriptPath))
        if '' not in sys.path:
            sys.path += ['']
        if 'DEBUG' in os.environ:
            self._console.redirectStdin(True)
            self._console.redirectStdout(True)
            self._console.redirectStderr(True)
        scriptLocals = self.scriptLocals()
        scriptLocals['__file__'] = scriptPath   # Let the script know where it is being run from.
        try:
            execfile(os.path.basename(scriptPath), scriptLocals)
        finally:
            os.chdir(prevDir)
            if 'DEBUG' in os.environ:
                self._console.redirectStdin(False)
                self._console.redirectStdout(False)
                self._console.redirectStderr(False)
        
                runTime = datetime.datetime.now() - startTime
                self._console.writeOut('# Ran ' + scriptName + ' in ' + str(round(runTime.seconds + runTime.microseconds / 1000000.0, 2)) + ' seconds.\n')
            
            self.display._suppressRefresh = refreshWasSuppressed
            
            self.Thaw()
            
            # Put up a new prompt if the script produced any output.
            if self._console.promptPosEnd != self._console.GetTextLength():
                self._console.prompt()
            
            while self._progressNestingLevel > 0:
                self.endProgress()
    
        
    def _profileScript(self, scriptPath):
        import cProfile, pstats
        profilePath = scriptPath + '.profile'
        print 'Saving profile to ' + profilePath + ' ...'
        cProfile.runctx('self.runScript(' + repr(scriptPath) + ')', {}, {'self': self}, filename = profilePath)
        p = pstats.Stats(profilePath)
        p.strip_dirs().sort_stats('time').print_stats(30)
    
        
    def onRunScript(self, event_):
        dlg = wx.FileDialog(None, 'Choose a script to run', './Scripts', '', '*.py', wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            scriptPath = dlg.GetPath()
        else:
            scriptPath = None
        dlg.Destroy()
        self.Update()   # Cosmetic tweak to make sure the file dialog gets fully erased before the script runs.
        if scriptPath is not None:
            try:
                self.runScript(scriptPath)
            except:
                (exceptionType, exceptionValue, exceptionTraceback) = sys.exc_info()
                frames = traceback.extract_tb(exceptionTraceback)[2:]
                wx.MessageBox(str(exceptionValue) + ' (' + exceptionType.__name__ + ')' + '\n\nTraceback:\n' + ''.join(traceback.format_list(frames)), gettext('An error occurred while running the script:'), parent = self, style = wx.ICON_ERROR | wx.OK)
        self.Show(True)
        
        # Turn off bulk loading in case the script forgot to.
        self.display.network.setBulkLoading(False)
    
    
    def onUndo(self, event_):
        self._console.Undo()
    
    
    def onRedo(self, event_):
        self._console.Redo()
    
    
    def onCut(self, event_):
        self._console.Cut()
    
    
    def onCopy(self, event_):
        self._console.Copy()
    
    
    def onPaste(self, event_):
        self._console.Paste()
    
    
    def onSelectAll(self, event_):
        if self.FindFocus() == self.display:
            self.display.selectAll()
        else:
            self._console.SelectAll()
    
    
    def onClear(self, event_):
        self._console.ClearAll()
        self._console.prompt()
    
    
    def onFind(self, event_):
        if self.finder is None:
            self.finder = Finder(self, -1, gettext('Finder'), pos = (-1, -1))
        
        if self.finder.ShowModal() == wx.ID_OK:
            self.display.selectObjectsMatching(self.finder.predicate)
            if not any(self.display.selection()):
                wx.Bell()
    
    
    def OnUseMouseOverSelecting(self, event_):
        self.display.setUseMouseOverSelecting(not self.display.useMouseOverSelecting())
    
    
    def onDecreaseSelectionHighlightDepth(self, event_):
        self.display.setSelectionHighlightDepth(self.display.selectionHighlightDepth() - 1)
    
    
    def onIncreaseSelectionHighlightDepth(self, event_):
        self.display.setSelectionHighlightDepth(self.display.selectionHighlightDepth() + 1)
    
    
    def onHighlightOnlyWithinSelection(self, event_):
        self.display.setHighlightOnlyWithinSelection(not self.display.highlightOnlyWithinSelection())
    
    
    def onShowHideRegionNames(self, event_):
        self.display.setShowRegionNames(not self.display.showRegionNames())
    
    
    def onShowHideNeuronNames(self, event_):
        self.display.setShowNeuronNames(not self.display.showNeuronNames())

    def onShowHideNeuronNamesOnSelection(self, event_):
        self.display.setShowNeuronNamesOnSelection(not self.display.showNeuronNamesOnSelection())

    def onPrintHideNeuronNamesOnSelection(self, event_):
        self.display.setPrintNeuronNamesOnSelection(not self.display.printNeuronNamesOnSelection())

    def onHideUnselectedOnSelection(self, event_):
        self.display.setHideUnselectedNeurons(not self.display.hideUnselectedNeurons())

    def onHideSynapsesOnConnections(self, event_):
        self.display.setHideSynapsesOnConnections(not self.display.hideSynapsesOnConnections())
    
    def onSetLabelsFloatOnTop(self, event_):
        self.display.setLabelsFloatOnTop(not self.display.labelsFloatOnTop())
    
    
    def onShowFlow(self, event_):
        self.display.setShowFlow(not self.display.showFlow())
    
    
    def onUseGhosts(self, event_):
        self.display.setUseGhosts(not self.display.useGhosts())
    
    
    def onUpdateLayoutUI(self, event):
        menuItem = self.GetMenuBar().FindItemById(event.GetId())
        layoutClass = self.layoutClasses[event.GetId()]
        menuItem.Enable(layoutClass.canLayoutDisplay(self.display))
    
    
    def onShowCompass(self, event_):
        self.display.setShowCompass(not self.display.isShowingCompass())
    
    
    def onResetView(self, event_):
        self.display.resetView()
    
    
    def onZoomToFit(self, event_):
        self.display.zoomToFit()
    
    
    def onZoomToSelection(self, event_):
        self.display.zoomToSelection()
    
    
    def onZoomIn(self, event_):
        self.display.zoomIn()
    
    
    def onZoomOut(self, event_):
        self.display.zoomOut()
    
    
    def onPan(self, event_):
        self.display.setNavigationMode(display.display.PANNING_MODE)
    
    
    def onRotate(self, event_):
        self.display.setNavigationMode(display.display.ROTATING_MODE)
    
    
    def onAddRegion(self, event_):
        self.display.addObjectOfClass(Region)
    
    
    def onAddNeuron(self, event_):
        self.display.addObjectOfClass(Neuron)
    
    
    def onAddMuscle(self, event_):
        self.display.addObjectOfClass(Muscle)
    
    
    def onAddStimulus(self, event_):
        self.display.addObjectOfClass(Stimulus)
    
    
    def onDeleteObjects(self, event_):
        # TODO: how to allow removing from display OR removing from network and all displays?
        
        message = gettext('Are you sure you wish to delete the selected objects?')
        if platform.system() == 'Darwin':
            result = wx.MessageBox('', message, style = wx.ICON_QUESTION | wx.YES_NO)
        else:
            result = wx.MessageBox(message, gettext('Neuroptikon'), style = wx.ICON_QUESTION | wx.YES_NO)
        if result == wx.YES:
            for visible in self.display.selection():
                if visible.client:
                    self.display.network.removeObject(visible.client)
                else:
                    self.display.removeVisible(visible)
    
    
    def onCloseWindow(self, event_):
        self.Close()
    
    
    def onClose(self, event):
        doClose = True
        
        if self._modified:
            if platform.system() != 'Darwin':
                message = gettext('Your changes will be lost if you don\'t save them.') + '\n\n' + gettext('Do you want to save the changes you made to "%s"?') % (self.display.network.name())
                caption = gettext('Neuroptikon')
            else:
                message = gettext('Your changes will be lost if you don\'t save them.')
                caption = gettext('Do you want to save the changes you made to "%s"?') % (self.display.network.name())
            result = wx.MessageBox( message, caption, parent = self, style = wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)
            if result == wx.YES:
                doClose = self.onSaveNetwork()
            elif result == wx.CANCEL:
                doClose = False
        
        if doClose:
            self.display.selectObjects([])
            wx.GetApp().inspector.inspectDisplay(None)
            network = self.display.network
            dispatcher.disconnect(self.networkDidChangeSavePath, ('set', 'savePath'), network)
            self.display.close()
            self.display = None
            self.Destroy()
            wx.GetApp().displayWasClosed(self)
            if not any(network.displays):
                wx.GetApp().releaseNetwork(network)
        elif event.GetEventType() == wx.wxEVT_CLOSE_WINDOW:
            event.Veto()
    
    
    def indentXMLElement(self, element, level = 0):
        i = "\n" + level * "\t"
        if len(element):
            if not element.text or not element.text.strip():
                element.text = i + "\t"
            if not element.tail or not element.tail.strip():
                element.tail = i
            for element in element:
                self.indentXMLElement(element, level + 1)
            if not element.tail or not element.tail.strip():
                element.tail = i
        else:
            if level and (not element.tail or not element.tail.strip()):
                element.tail = i
    
    
    def saveNetworkAndDisplaysAsXML(self, savePath, saveDisplays = True):
        xmlRoot = ElementTree.Element('Neuroptikon')
        network = self.display.network
        
        # Serialize the network
        networkElement = network._toXMLElement(xmlRoot)
        if networkElement is None:
            raise ValueError, gettext('Could not save the network')
        
        if saveDisplays:
            # Serialize the display(s)
            for display in network.displays:
                frameElement = display.GetTopLevelParent()._toXMLElement(xmlRoot)
                if frameElement is None:
                    raise ValueError, gettext('Could not save one of the windows')
        
        self.indentXMLElement(xmlRoot)
        xmlTree = ElementTree.ElementTree(xmlRoot)
        xmlTree.write(savePath)
        
        # To test the contents of the output use:
        # xmllint --noout --schema Source/Neuroptikon_v1.0.xsd Test.xml
    
    
    def saveNetworkAndDisplaysAsScript(self, savePath, saveNetwork = True, saveDisplays = True):
        scriptRefs = {}
        network = self.display.network
        
        if saveDisplays:
            if len(network.displays) == 1:
                scriptRefs[self.display] = 'display'
            else:
                for display in network.displays:
                    scriptRefs[display] = 'display' + str(network.displays.index(display))
        
        if not saveNetwork:
            # Attempt to create script refs for all objects using the network.find* methods.
            objectNames = {}
            for networkObject in network.objects:
                if networkObject._includeInScript():
                    objectName = networkObject.name
                    defaultName = networkObject.defaultName()
                    
                    # Make sure the object has a name.
                    if not objectName and not defaultName:
                        for display in network.displays:
                            display.selectObject(networkObject)
                        raise ValueError, gettext('The display of the selected object cannot be saved because it does not have a name.')
                    
                    # Make sure the name is unique.
                    if objectName:
                        nameKey = networkObject.__class__.__name__ + ': ' + objectName
                        if nameKey in objectNames:
                            for display in network.displays:
                                display.selectObjects([networkObject, objectNames[nameKey]])
                            raise ValueError, gettext('The display cannot be saved because there is more than one %s with the name \'%s\'.') % (networkObject.__class__.__name__.lower(), objectName)
                    else:
                        nameKey = networkObject.__class__.__name__ + ': ' + defaultName
                        if nameKey in objectNames:
                            for display in network.displays:
                                display.selectObjects([networkObject, objectNames[nameKey]])
                            raise ValueError, gettext('The display cannot be saved because there is more than one %s with the default name \'%s\'.') % (networkObject.__class__.__name__.lower(), defaultName)
                    
                    # Create the script ref.
                    objectNames[nameKey] = networkObject
                    if 'find' + networkObject.__class__.__name__ in dir(network):
                        prefix = 'network.find' + networkObject.__class__.__name__ + '(\''
                    else:
                        prefix = 'network.findObject(' + networkObject.__class__.__name__ + ', \''
                    if objectName:
                        scriptRefs[networkObject.networkId] = prefix + objectName + '\')'
                    else:
                        scriptRefs[networkObject.networkId] = prefix + defaultName + '\', default = True)'
        
        scriptFile = open(savePath, 'w')
        
        try:
            # Serialize the network
            if saveNetwork:
                if saveDisplays:
                    for display in network.displays:
                        if not display.autoVisualize:
                            scriptFile.write(scriptRefs[display] + '.autoVisualize = False\n')
                    scriptFile.write('\n')
                network._toScriptFile(scriptFile, scriptRefs)
            else:
                scriptFile.write('anyOrphans = False\n')
            
            if saveDisplays:
                # Serialize the display(s)
                for display in network.displays:
                    displayRef = display.GetTopLevelParent()._toScriptFile(scriptFile, scriptRefs, saveNetwork)
                    if not saveNetwork:
                        scriptFile.write('\nfor visibles in ' + displayRef + '.visibles.itervalues():\n    for visible in visibles:\n        if visible.isOrphan():\n            anyOrphans = True\n')
                
                if not saveNetwork:
                    scriptFile.write('\nif anyOrphans:\n    showMessage(\'Some objects from the original network could not be found.\', \'The orphaned objects have been highlighted in red.\', isError = True)\n\n')
            else:
                scriptFile.write('\n# Reveal the default visualization\ndisplay.zoomToFit()\n')
        except:
            raise    # TODO: inform the user nicely
        finally:
            scriptFile.close()
    
    
    def onSaveNetwork(self, event_ = None):
        success = False
        
        network = self.display.network
        if network.savePath() is None:
            dlg = wx.FileDialog(None, gettext('Save as:'), '', 'Network.xml', '*.xml', wx.SAVE | wx.FD_OVERWRITE_PROMPT)
            if dlg.ShowModal() == wx.ID_OK:
                savePath = dlg.GetPath()
                if not savePath.endswith('.xml'):
                    savePath += '.xml'
                network.setSavePath(savePath)
            dlg.Destroy()
        
        if network.savePath() is not None:
            try:
                self.saveNetworkAndDisplaysAsXML(network.savePath())
                self.display.network.setModified(False)
                for display in network.displays:
                    display.GetTopLevelParent().setModified(False)
                success = True
            except:
                (exceptionType, exceptionValue, exceptionTraceback_) = sys.exc_info()
                wx.MessageBox(str(exceptionValue) + ' (' + exceptionType.__name__ + ')', gettext('The file could not be saved.'), parent = self, style = wx.ICON_ERROR | wx.OK)
        
        return success
    
    
    def onSaveNetworkAs(self, event_):
        network = self.display.network
        fileTypes = ['XML File', 'XML File (network only)', 'Python Script', 'Python Script (network only)', 'Python Script (display only)']
        fileExtensions = ['xml', 'xml', 'py', 'py', 'py']
        wildcard = ''
        for index in range(0, len(fileTypes)):
            if wildcard != '':
                wildcard += '|'
            wildcard += fileTypes[index] + '|' + fileExtensions[index]
        fileDialog = wx.FileDialog(None, gettext('Save As:'), '', '', wildcard, wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if network.savePath() == None:
            fileDialog.SetFilename('Network.xml')
        else:
            fileDialog.SetFilename(os.path.basename(network.savePath()))
        if fileDialog.ShowModal() == wx.ID_OK:
            filterIndex = fileDialog.GetFilterIndex()
            saveNetwork = (filterIndex != 4)
            saveDisplays = (filterIndex in [0, 2, 4])
            extension = fileExtensions[filterIndex]
            savePath = str(fileDialog.GetPath())
            if not savePath.endswith('.' + extension):
                savePath += '.' + extension
            try:
                if extension == 'xml':
                    network.setSavePath(savePath)
                    self.saveNetworkAndDisplaysAsXML(savePath, saveDisplays)
                    self.display.network.setModified(False)
                    for display in network.displays:
                        display.GetTopLevelParent().setModified(False)
                    # TODO: if only the network was saved and the diplay was changed then those changes could be lost...
                else:
                    self.saveNetworkAndDisplaysAsScript(savePath, saveNetwork, saveDisplays)
            except:
                (exceptionType, exceptionValue, exceptionTraceback_) = sys.exc_info()
                wx.MessageBox(exceptionType.__name__ + ": " + str(exceptionValue), gettext('The file could not be saved.'), parent = self, style = wx.ICON_ERROR | wx.OK)
        fileDialog.Destroy()
    
    
    def setModified(self, modified):
        if self._modified != modified:
            self._modified = modified
            if platform.system() == 'Darwin':
                # Use ctypes to call into the Carbon API to set the window's modified state.  When modified is True this causes the close button to be drawn with a dot inside it.
                # Use wx.CallAfter otherwise the dot won't show up until the window is resized, deactivated or the mouse hovers over the button.
                wx.CallAfter(carbon.SetWindowModified, self.MacGetTopLevelWindowRef(), modified)
            elif platform.system() != 'Darwin':
                title = self.GetTitle()
                if modified and not title.endswith('*'):
                    self.SetTitle(title + '*')
                elif not modified and title.endswith('*'):
                    self.SetTitle(title[:-1])
    
    
    def isModified(self):
        return self._modified
    
    
    def beginProgress(self, message = None, visualDelay = 1.0):
        """
        Display a message that a lengthy task has begun.
        
        Each call to this method must be balanced by a call to :meth:`endProgress <display.display.Display.endProgress>`.  Any number of :meth:`updateProgress <display.display.Display.updateProgress>` calls can be made in the interim.  Calls to this method can be nested as long as the right number of :meth:`endProgress <display.display.Display.endProgress>` calls are made.
        
        The visualDelay argument indicates how many seconds to wait until the progress user interface is shown.  This avoids flashing the interface open and closed for tasks that end up running quickly.
        """
        
        self._progressMessage = message
        
        self._progressNestingLevel += 1
        if self._progressNestingLevel == 1:
            self._progressShouldContinue = True
            
            # Have the UI pop up after visualDelay seconds.
            self._progressDisplayTime = datetime.datetime.now() + datetime.timedelta(0, visualDelay)
            wx.CallLater(visualDelay, self._updateProgress)
    
    
    def _updateProgress(self, forceDisplay = False):
        if self._progressNestingLevel > 0:
            if forceDisplay or datetime.datetime.now() > self._progressDisplayTime:
                if self._progressDialog is None:
                    self._progressDialog = wx.ProgressDialog(gettext('Neuroptikon'), 'some long text that will make the dialog a nice width', parent = self, style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_REMAINING_TIME)
                
                if self._progressFractionComplete is None:
                    if not self._progressDialog.Pulse(gettext(self._progressMessage or ''))[0]:
                        self._progressShouldContinue = False
                else:
                    if not self._progressDialog.Update(100.0 * self._progressFractionComplete, gettext(self._progressMessage or ''))[0]:
                        self._progressShouldContinue = False
            
            self._progressLastUpdate = datetime.datetime.now()
    
    
    def updateProgress(self, message = None, fractionComplete = None, forceDisplay = False):
        """
        Update the message and/or completion fraction during a lengthy task.
        
        If the user has pressed the Cancel button then this method will return False and the task should be aborted.
        """
        
        # Throttle GUI updates to avoid a performance hit.
        if message is not None:
            self._progressMessage = message
        self._progressFractionComplete = fractionComplete
        if datetime.datetime.now() - self._progressLastUpdate > self._progressUpdateDelta:
            self._updateProgress(forceDisplay)
        
        # Allow events to be processed while the task is running.
        wx.Yield()
        
        return self._progressShouldContinue
    
    
    def endProgress(self):
        """
        Indicate that the lengthy task has ended.
        """
        
        self._progressNestingLevel -= 1
        
        if self._progressNestingLevel == 0 and self._progressDialog is not None:
            if platform.system() == 'Darwin':
                # Workaround a wx bug: http://trac.wxwidgets.org/ticket/4795
                self._progressDialog.EndModal(wx.ID_CANCEL)
            self._progressDialog.Destroy()
            self._progressDialog = None
    
    
    def showMessage(self, message, subMessage = None, isError = False):
        """
        Display a display-specific message to the user.
        """
        
        self.Thaw()
        if platform.system() == 'Darwin':
            wx.MessageBox(subMessage, message or '', style = (wx.ICON_ERROR if isError else wx.ICON_INFORMATION) | wx.OK)
        else:
            wx.MessageBox('Neuroptikon', (message + '\n\n' + subMessage if message else subMessage or ''), style = (wx.ICON_ERROR if isError else wx.ICON_INFORMATION) | wx.OK)
        self.Freeze()
