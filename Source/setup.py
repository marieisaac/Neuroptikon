"""
py2app/py2exe build script for Neuroptikon

Usage (Mac OS X):
    python setup.py --quiet py2app

Usage (Windows):
    python setup.py --quiet py2exe
"""

# Make sure setuptools is installed.
import ez_setup
ez_setup.use_setuptools()

import os, platform, sys
from setuptools import setup

def purge_dir(path):
    if os.path.exists(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(path)

app_scripts = ['Neuroptikon.py']

import __version__
app_version = __version__.version

setup_options = dict()

resources = ['Images', 'Inspectors', 'Layouts', 'Neuroptikon_v1.0.xsd', 'Ontologies', 'Shapes', 'Textures']
resources += ['Display/FlowShader.vert', 'Display/FlowShader.frag', 'Display/CullFaces.osg']
includes = ['wx', 'xlrd']
excludes = ['Inspectors', 'Layouts', 'matplotlib', 'scipy', 'Shapes']

sys.path += ['lib/CrossPlatform', 'lib/' + platform.system()]

# Purge and then rebuild the documentation with Sphinx
purge_dir('Documentation/build')
try:
    from sphinx import main
except:
    print 'You must have sphinx installed and in the Python path to build the Neuroptikon package.  See <http://sphinx.pocoo.org/>.'
result = main(['-q', '-b', 'html', 'Documentation/Source', 'Documentation/build/Documentation'])
if result != 0:
    sys.exit(result)

if sys.platform == 'darwin':

    # Mac build notes:
    # 1. Install Python from http://www.python.org/ftp/python/2.5.4/python-2.5.4-macosx.dmg
    # 2. Make that python active: sudo python_select python25 (?)
    # 3. sudo easy_install py2app
    # 4. sudo easy_install numpy
    # 5. Install wxPython from http://downloads.sourceforge.net/wxpython/wxPython2.8-osx-unicode-2.8.9.2-universal-py2.5.dmg
    # 6. export PYTHONPATH=/usr/local/lib/wxPython-unicode/lib/python2.5/site-packages:/Library/Python/2.5
    # 7. python setup.py --quiet py2app
    
    import wxversion
    wxversion.select('2.8')
    
    setup_options['setup_requires'] = ['py2app']
    setup_options['app'] = app_scripts
    
    py2app_options = dict()
    
    dist_dir = 'build/Neuroptikon ' + app_version
    purge_dir(dist_dir)
    py2app_options['dist_dir'] = dist_dir
    
    excludes += ['aetools', 'StdSuites.AppleScript_Suite']
    
    py2app_options['packages'] = includes
    py2app_options['excludes'] = excludes
    
    resources += ['../Artwork/Neuroptikon.icns']
    resources += ['lib/Darwin/fdp', 'lib/Darwin/graphviz']
    resources += ['lib/Darwin/osgdb_freetype.so', 'lib/Darwin/osgdb_osg.so', 'lib/Darwin/osgdb_qt.so']
    resources += ['Documentation/build/Documentation']
    py2app_options['resources'] = ','.join(resources)
    
    py2app_options['argv_emulation'] = True
    py2app_options['plist'] = dict()
    py2app_options['plist']['CFBundleIconFile'] = 'Neuroptikon.icns'
    py2app_options['plist']['PyResourcePackages'] = ['lib/python2.5/lib-dynload']
    py2app_options['plist']['LSEnvironment'] = dict(DYLD_LIBRARY_PATH = '../Resources')
    
    setup_options['options'] = dict(py2app = py2app_options)
    
elif sys.platform == 'win32':
    
    # Windows build notes:
    # - Install Enthought Python Distribution
    # - Install Inno Setup QuickStart Pack from http://jrsoftware.org/isdl.php
    # - move aside networkx(?) and pyxml site-packages
    # - python setup.py --quiet py2exe
    
    import py2exe
    
    setup_options['setup_requires'] = ['py2exe']
    setup_options['windows'] = [{'script': app_scripts[0], 'icon_resources':  [(0, '../Artwork/Neuroptikon.ico')]}]
    
    py2exe_options = dict()
    
    dist_dir = 'build/Neuroptikon ' + app_version
    purge_dir(dist_dir)
    py2exe_options['dist_dir'] = dist_dir
    
    py2exe_options['packages'] = includes
    py2exe_options['excludes'] = excludes + ['numarray', 'pyxml', 'Tkinter', '_tkinter']
    
    # py2exe doesn't support 'resources' so we have to add each file individually.
    # TODO: use glob instead?
    def addDataFiles(dataFilesList, dataDir):
        dataFiles = []
        for dataFileName in os.listdir(dataDir):
            dataFilePath = dataDir + os.sep + dataFileName
            if dataFileName != '.svn':
                if os.path.isdir(dataFilePath):
                    addDataFiles(dataFilesList, dataFilePath)
                else:
                    dataFiles.append(dataFilePath)
        if len(dataFiles) > 0:
            dataFilesList.append((dataDir, dataFiles))
    
    resources.append('Scripts')	# TBD: or add them via the installer?
    
    dataFilesList = []
    for resourceName in resources:
        if os.path.isdir(resourceName):
            addDataFiles(dataFilesList, resourceName)
        else:
            dataFilesList.append(('', [resourceName]))
    # Include all of the libraries that OSG needs.
    dataFilesList.append(('', ['lib/Windows/freetype6.dll', 'lib/Windows/libimage.dll', 'lib/Windows/libpng3.dll', 'lib/Windows/libpng12.dll', 'lib/Windows/librle3.dll', 'lib/Windows/libtiff3.dll']))
    # Include the OSG plug-ins we use.
    dataFilesList.append(('', ['lib/Windows/osgdb_freetype.dll', 'lib/Windows/osgdb_jpeg.dll', 'lib/Windows/osgdb_osg.dll', 'lib/Windows/osgdb_png.dll', 'lib/Windows/osgdb_tiff.dll']))
    setup_options['data_files'] = dataFilesList
    
    setup_options['options'] = dict(py2exe = py2exe_options)
else:
        pass	# TODO: Linux setup

setup(
    name = 'Neuroptikon', 
    version = app_version, 
    description = 'Neural circuit visualization', 
    url = 'http://openwiki.janelia.org/wiki/display/neuroptikon/', 
    **setup_options
)


import shutil
if sys.platform == 'darwin':
    scriptsDir = os.path.join(dist_dir, 'Sample Scripts')
    if os.path.exists(scriptsDir):
        shutil.rmtree(scriptsDir)
    shutil.copytree('Scripts', scriptsDir)
elif sys.platform == 'win32':
    shutil.copytree(os.path.join('Documentation/build/Documentation'), os.path.join(dist_dir, 'Documentation'))

# Strip out any .pyc or .pyo files.
import os
for root, dirs, files in os.walk(dist_dir, topdown=False):
    for name in files:
        if os.path.splitext(name)[1] in ['.pyc', '.pyo']:
                os.remove(os.path.join(root, name))


from subprocess import call
if sys.platform == 'darwin':
    # Create the disk image
    dmgPath = 'build/Neuroptikon ' + app_version + '.dmg'
    if os.path.exists(dmgPath):
        os.remove(dmgPath)
    print 'Creating disk image...'
    print 'hdiutil create -srcfolder \'' + dist_dir + '\' -format UDZO "' + dmgPath + '"'
    retcode = call('hdiutil create -srcfolder \'' + dist_dir + '\' -format UDZO "' + dmgPath + '"', shell=True)
    if retcode < 0:
        print "Could not create disk image"
    else:
        # Open the disk image in the Finder so we can check it out.
        call('open "' + dmgPath + '"', shell=True)
elif sys.platform == 'win32':
    # Create the installer
    print 'Creating installer...'
    retcode = call('C:\Program Files\Inno Setup 5\iscc.exe /Q /O"build" "/dAPP_VERSION=' + app_version + '" Neuroptikon.iss')
    if retcode != 0:
        print "Could not create the installer"
