import wx, wx.grid
import os, sys, weakref
from Network.Attribute import Attribute


class GridCellAttributeTypeRenderer(wx.grid.PyGridCellRenderer):
    
    def __init__(self, inspector):
        self.inspectorRef = weakref.ref(inspector)
            
        wx.grid.PyGridCellRenderer.__init__(self)
    
    
    def Draw(self, grid, attr, drawingContext, rect, row, col, isSelected):
        drawingContext.SetClippingRegion( rect.x, rect.y, rect.width, rect.height )
        
        # Draw the background
        if isSelected:
            drawingContext.SetBrush(wx.Brush(wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT), wx.SOLID))
        else:
            drawingContext.SetBrush(wx.Brush(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW), wx.SOLID))
        try:
            drawingContext.SetPen(wx.TRANSPARENT_PEN)
            drawingContext.DrawRectangle(rect.x, rect.y, rect.width, rect.height)
        finally:
            drawingContext.SetPen(wx.NullPen)
            drawingContext.SetBrush(wx.NullBrush)
        
        # Draw the appropriate icon
        try:
            value = grid.GetCellValue(row, col)
            if value in self.inspectorRef().icons:
                icon = self.inspectorRef().icons[value]
                drawingContext.DrawBitmap(icon, rect.x + rect.width / 2 - 8, rect.y + rect.height / 2 - 8, True)
        finally:
            drawingContext.DestroyClippingRegion()
    
    
    def GetBestSize(self, grid, attr, drawingContext, row, col):
        return wx.Size(16, 16)
    

    def Clone(self):
        return GridCellChoiceEditor(self.inspectorRef())

