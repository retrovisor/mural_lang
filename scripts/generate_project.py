#!/usr/bin/env python3
"""Generate Mural.xcodeproj using only Python's standard library."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1] / 'apps' / 'ios'
existing_project = root/'Mural.xcodeproj'/'project.pbxproj'
existing_team = re.search(r'DEVELOPMENT_TEAM\s*=\s*"?([A-Z0-9]+)', existing_project.read_text()) if existing_project.exists() else None
if existing_team:
    local_settings = root/'Config'/'Local.xcconfig'
    local_settings.parent.mkdir(exist_ok=True)
    contents = local_settings.read_text() if local_settings.exists() else '// Personal signing settings. Do not commit.\n'
    setting = 'DEVELOPMENT_TEAM = ' + existing_team.group(1)
    if re.search(r'^DEVELOPMENT_TEAM\s*=.*$', contents, re.MULTILINE):
        contents = re.sub(r'^DEVELOPMENT_TEAM\s*=.*$', setting, contents, flags=re.MULTILINE)
    else:
        contents += '\n' + setting + '\n'
    local_settings.write_text(contents)
objects = {}
def uid(name): return hashlib.sha1(name.encode()).hexdigest()[:24].upper()
def add(identifier, isa, **fields):
    i = uid(identifier); objects[i] = dict(isa=isa, **fields); return i
_UNQUOTED = re.compile(r'^[A-Za-z0-9_$./]+$')
def scalar(value):
    # Same quoting rule as Xcode: bare token when it is safe, quoted otherwise.
    text = str(value)
    return text if text and _UNQUOTED.match(text) else json.dumps(text, ensure_ascii=False)
_PHASE_NAMES = {'PBXSourcesBuildPhase': 'Sources', 'PBXFrameworksBuildPhase': 'Frameworks', 'PBXResourcesBuildPhase': 'Resources'}
def comment_for(identifier):
    # The "/* name */" annotations Xcode writes after object references. Parsers
    # such as the `xcode` npm package (used by EAS CLI and @expo/config-plugins)
    # read list entries as {value, comment}, so the annotations are not cosmetic.
    obj = objects.get(identifier)
    if obj is None: return None
    isa = obj['isa']
    if isa == 'PBXProject': return 'Project object'
    if isa in _PHASE_NAMES: return _PHASE_NAMES[isa]
    if isa == 'PBXBuildFile':
        ref = obj.get('fileRef') or obj.get('productRef')
        phase = next((_PHASE_NAMES[o['isa']] for o in objects.values() if o['isa'] in _PHASE_NAMES and identifier in o.get('files', [])), None)
        base = comment_for(ref) or ref
        return base + ' in ' + phase if phase else base
    if isa == 'XCConfigurationList':
        owner = next((o for o in objects.values() if o.get('buildConfigurationList') == identifier), None)
        return 'Build configuration list for ' + owner['isa'] + ' "' + str(owner.get('name', 'Mural')) + '"' if owner else 'Build configuration list'
    if isa == 'XCRemoteSwiftPackageReference': return isa + ' "' + obj['repositoryURL'].rsplit('/', 1)[-1].removesuffix('.git') + '"'
    if isa == 'XCLocalSwiftPackageReference': return isa + ' "' + obj['relativePath'] + '"'
    if isa == 'XCSwiftPackageProductDependency': return obj['productName']
    if isa in ('PBXContainerItemProxy', 'PBXTargetDependency'): return isa
    if 'name' in obj: return str(obj['name'])
    if 'path' in obj: return str(obj['path']).rsplit('/', 1)[-1]
    return None
def reference(value, key=None):
    text = scalar(value)
    if key in ('remoteGlobalIDString', 'TestTargetID'): return text
    comment = comment_for(value) if isinstance(value, str) and value in objects else None
    return text + ' /* ' + comment + ' */' if comment else text
def encode(value, depth=0, key=None):
    tab = '\t' * depth
    if isinstance(value, dict):
        if not value: return '{\n' + tab + '}'
        return '{\n' + ''.join(tab + '\t' + scalar(k) + ' = ' + encode(v, depth + 1, k) + ';\n' for k, v in value.items()) + tab + '}'
    if isinstance(value, list):
        return '(\n' + ''.join(tab + '\t' + encode(v, depth + 1) + ',\n' for v in value) + tab + ')'
    return reference(value, key)
def encode_project(root_object):
    # Xcode's own layout: objects grouped into "/* Begin <isa> section */" blocks.
    # Tools that parse pbxproj files (EAS CLI, @expo/config-plugins, the `xcode`
    # npm package) rely on those section markers to find targets and settings.
    sections = {}
    for identifier, obj in objects.items():
        sections.setdefault(obj['isa'], []).append(identifier)
    lines = ['// !$*UTF8*$!', '{', '\tarchiveVersion = 1;', '\tclasses = {', '\t};', '\tobjectVersion = 60;', '\tobjects = {', '']
    for isa in sorted(sections):
        lines.append('/* Begin ' + isa + ' section */')
        for identifier in sections[isa]:
            lines.append('\t\t' + reference(identifier) + ' = ' + encode(objects[identifier], 2) + ';')
        lines.append('/* End ' + isa + ' section */')
        lines.append('')
    lines += ['\t};', '\trootObject = ' + reference(root_object) + ';', '}', '']
    return '\n'.join(lines)

sources, refs = [], []
for file in sorted((root/'App').rglob('*.swift')):
    path = str(file.relative_to(root))
    ref = add(path, 'PBXFileReference', lastKnownFileType='sourcecode.swift', path=path, sourceTree='<group>')
    refs.append(ref); sources.append(add(path+'build','PBXBuildFile',fileRef=ref))
asset = add('assets','PBXFileReference',lastKnownFileType='folder.assetcatalog',path='App/Assets.xcassets',sourceTree='<group>')
refs.append(asset)
notices = add('notices','PBXFileReference',lastKnownFileType='text',path='App/ThirdPartyNotices.txt',sourceTree='<group>')
refs.append(notices)
privacy = add('privacy','PBXFileReference',lastKnownFileType='text.xml',path='App/PrivacyInfo.xcprivacy',sourceTree='<group>')
refs.append(privacy)
signing = add('signing','PBXFileReference',lastKnownFileType='text.xcconfig',path='Config/Signing.xcconfig',sourceTree='<group>')
refs.append(signing)
testSource = add('testSource','PBXFileReference',lastKnownFileType='sourcecode.swift',path='UITests/MuralUITests.swift',sourceTree='<group>')
refs.append(testSource)
product = add('product','PBXFileReference',explicitFileType='wrapper.application',path='Mural.app',sourceTree='BUILT_PRODUCTS_DIR')
testProduct = add('testProduct','PBXFileReference',explicitFileType='wrapper.cfbundle',path='MuralUITests.xctest',sourceTree='BUILT_PRODUCTS_DIR')
products = add('products','PBXGroup',children=[product,testProduct],name='Products',sourceTree='<group>')
group = add('main','PBXGroup',children=refs+[products],sourceTree='<group>')
corePackage = add('corePackage','XCLocalSwiftPackageReference',relativePath='.')
rtcPackage = add('rtcPackage','XCRemoteSwiftPackageReference',repositoryURL='https://github.com/stasel/WebRTC.git',requirement={'kind':'exactVersion','version':'152.0.0'})
core = add('core','XCSwiftPackageProductDependency',package=corePackage,productName='MuralCore')
rtc = add('rtc','XCSwiftPackageProductDependency',package=rtcPackage,productName='WebRTC')
frameworks = add('frameworks','PBXFrameworksBuildPhase',buildActionMask=2147483647,files=[add('coreBuild','PBXBuildFile',productRef=core),add('rtcBuild','PBXBuildFile',productRef=rtc)],runOnlyForDeploymentPostprocessing=0)
sourcePhase = add('sources','PBXSourcesBuildPhase',buildActionMask=2147483647,files=sources,runOnlyForDeploymentPostprocessing=0)
resources = add('resources','PBXResourcesBuildPhase',buildActionMask=2147483647,files=[add('assetsBuild','PBXBuildFile',fileRef=asset),add('noticesBuild','PBXBuildFile',fileRef=notices),add('privacyBuild','PBXBuildFile',fileRef=privacy)],runOnlyForDeploymentPostprocessing=0)
common = {'SDKROOT':'iphoneos','IPHONEOS_DEPLOYMENT_TARGET':'26.1','SWIFT_VERSION':'5.0','CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','SWIFT_STRICT_CONCURRENCY':'targeted'}
targetSettings = {'PRODUCT_BUNDLE_IDENTIFIER':'is.vivatok.mural','PRODUCT_NAME':'$(TARGET_NAME)','TARGETED_DEVICE_FAMILY':'1','GENERATE_INFOPLIST_FILE':'NO','INFOPLIST_FILE':'App/Info.plist','CODE_SIGN_STYLE':'Automatic','MARKETING_VERSION':'0.1.0','CURRENT_PROJECT_VERSION':'1','ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME':'AccentColor','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks'],'ENABLE_PREVIEWS':'YES','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator'}
targetSettings.update({'CODE_SIGN_ENTITLEMENTS':'$(MURAL_APPLE_ENTITLEMENTS)',
                      'SWIFT_ACTIVE_COMPILATION_CONDITIONS':'$(inherited) $(MURAL_APPLE_SWIFT_FLAGS)'})
def configs(prefix, settings):
    ids=[]
    for name in ['Debug','Release']:
        s=dict(settings)
        if prefix=='project':
            s.update({'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if name=='Debug' else '-O','DEBUG_INFORMATION_FORMAT':'dwarf' if name=='Debug' else 'dwarf-with-dsym'})
            if name=='Debug': s['SWIFT_ACTIVE_COMPILATION_CONDITIONS']='DEBUG'
        fields = {'buildSettings':s,'name':name}
        if prefix in ['target', 'tests']: fields['baseConfigurationReference'] = signing
        ids.append(add(prefix+name,'XCBuildConfiguration',**fields))
    return add(prefix+'configs','XCConfigurationList',buildConfigurations=ids,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
target=add('target','PBXNativeTarget',buildConfigurationList=configs('target',targetSettings),buildPhases=[sourcePhase,frameworks,resources],buildRules=[],dependencies=[],name='Mural',packageProductDependencies=[core,rtc],productName='Mural',productReference=product,productType='com.apple.product-type.application')
testSources = add('testSources','PBXSourcesBuildPhase',buildActionMask=2147483647,files=[add('testBuild','PBXBuildFile',fileRef=testSource)],runOnlyForDeploymentPostprocessing=0)
proxy = add('testProxy','PBXContainerItemProxy',containerPortal=uid('project'),proxyType=1,remoteGlobalIDString=target,remoteInfo='Mural')
dependency=add('testDependency','PBXTargetDependency',target=target,targetProxy=proxy)
testTarget=add('testTarget','PBXNativeTarget',buildConfigurationList=configs('tests',{'PRODUCT_BUNDLE_IDENTIFIER':'is.vivatok.mural.uitests','PRODUCT_NAME':'$(TARGET_NAME)','GENERATE_INFOPLIST_FILE':'YES','TEST_TARGET_NAME':'Mural','TARGETED_DEVICE_FAMILY':'1','CODE_SIGN_STYLE':'Automatic'}),buildPhases=[testSources],buildRules=[],dependencies=[dependency],name='MuralUITests',productName='MuralUITests',productReference=testProduct,productType='com.apple.product-type.bundle.ui-testing')
project=add('project','PBXProject',attributes={'BuildIndependentTargetsInParallel':'YES','LastUpgradeCheck':'2640','TargetAttributes':{target:{'CreatedOnToolsVersion':'26.4'},testTarget:{'CreatedOnToolsVersion':'26.4','TestTargetID':target}}},buildConfigurationList=configs('project',common),compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings=0,knownRegions=['en','nb','Base'],mainGroup=group,packageReferences=[corePackage,rtcPackage],productRefGroup=products,projectDirPath='',projectRoot='',targets=[target,testTarget])
folder=root/'Mural.xcodeproj';folder.mkdir(exist_ok=True)
folder.joinpath('project.pbxproj').write_text(encode_project(project))
scheme=folder/'xcshareddata'/'xcschemes';scheme.mkdir(parents=True,exist_ok=True)
scheme.joinpath('Mural.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2640" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="Mural.app" BlueprintName="Mural" ReferencedContainer="container:Mural.xcodeproj"/></BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{testTarget}" BuildableName="MuralUITests.xctest" BlueprintName="MuralUITests" ReferencedContainer="container:Mural.xcodeproj"/></TestableReference></Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="Mural.app" BlueprintName="Mural" ReferencedContainer="container:Mural.xcodeproj"/></BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"/>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''')
print('Generated Mural.xcodeproj')
