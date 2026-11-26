[app]

# title of your application
title = JARVIS_AI

# project root directory. default = The parent directory of input_file
project_dir = .

# source file entry point path. default = main.py
input_file = desktop_main.py

# directory where the executable output is generated
exec_directory = dist/desktop

# path to the project file relative to project_dir
project_file =

# application icon
icon = desktop/resources/icons/jarvis.ico

[python]

# python packages to install
packages = Nuitka==4.1.1

# buildozer = for deploying Android application
android_packages = buildozer==1.6.0,cython==0.29.33

[qt]

# paths to required qml files. comma separated
qml_files =

# excluded qml plugin binaries
excluded_qml_plugins =

# qt modules used. comma separated
modules = Core,Gui,Network,Widgets

# Windows-only Qt plugins needed by the PySide6 Widgets desktop app (no macOS/Linux plugins)
plugins = accessiblebridge,generic,iconengines,imageformats,networkaccess,networkinformation,platforminputcontexts,platforms,styles,tls

[android]

# path to pyside wheel
wheel_pyside =

# path to shiboken wheel
wheel_shiboken =

# plugins to be copied to libs folder of the packaged application. comma separated
plugins =

[ios]

# path to pyside wheel
wheel_pyside =

# path to shiboken wheel
wheel_shiboken =

# path to python.xcframework
xcframework_path =

# reverse-dns bundle identifier, eg = com.example.myapp
# default (like xcode's own placeholder) = com.example.<app name, alphanumeric only>
bundle_id =

# apple developer team id, used for code signing. only required for device builds
team_id =

# app version (cfbundleshortversionstring)
version = 1.0

# minimum ios deployment target. default = read from the PySide6 wheel's embedded
# qt-for-ios kit
deployment_target =

# path to an .entitlements file, relative to project_dir
entitlements =

# code signing style. possible values = [Automatic, Manual]
signing_style = Automatic

# extra header search paths, relative to project_dir. comma separated
header_search_paths =

[nuitka]

# usage description for permissions requested by the app as found in the info.plist file
# of the app bundle. comma separated
# eg = extra_args = --show-modules --follow-stdlib
macos.permissions =

# mode of using nuitka. accepts standalone or onefile. default = standalone
mode = standalone

# specify any extra nuitka arguments (Windows MSVC x64, package data for audio/ONNX, static icon & .env.example template)
extra_args = --quiet --noinclude-qt-translations --msvc=latest --nofollow-import-to=pytest --nofollow-import-to=tests --include-data-file=desktop/resources/icons/jarvis.ico=desktop/resources/icons/jarvis.ico --include-data-file=.env.example=.env.example --include-package-data=sounddevice --include-package-data=faster_whisper --include-package-data=piper --include-package-data=openwakeword --include-package-data=onnxruntime

[buildozer]

# build mode
# possible values = ["aarch64", "x86_64"]
# release creates a .aab, while debug creates a .apk
mode = debug

# path to pyside6 and shiboken6 recipe dir
recipe_dir =

# path to extra qt android .jar files to be loaded by the application
jars_dir =

# if empty, uses default ndk path downloaded by buildozer
ndk_path =

# if empty, uses default sdk path downloaded by buildozer
sdk_path =

# other libraries to be loaded at app startup. comma separated.
local_libs =

# architecture of deployed platform
arch =
