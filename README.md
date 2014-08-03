onemake
=======

onemake is C/C++ build system built for Orandea Game Engine (open sourced as openoge).

It is design to fit following requirements:

* Very fast
* Easily to crosscompile
* Easily to build modular project


Manifests
=========

onemake is written in Python, and use JSON as manifest format.

onemake has two types of manifests:

* onemake.json: describes project structure
* profiles: describes build target settings

onemake.json
------------

onemake.json is a json object whose keys are the names of your projects. Here are some simple sample:

File tree
    |-onemake.json
    |-system
    |  |-include
    |  |-src
    |-graphics
    |  |-include
    |  |-internal_include
    |  |-src
    |-audio
    |  |-include
    |  |-src
    |-demo
    |  |-include
    |  |-src

onemake.json
    {
        "oge_system": {
            "directory": "system",
            "type": "library",
            "output_headers": true
        },

        "oge_graphics": {
            "directory": "graphics",
            "type": "library",
            "output_headers": true,
            "depends": ["oge_system"]
        },

        "oge_audio": {
            "directory": "audio",
            "type": "library",
            "output_headers": true,
            "depends": ["oge_system"]
        },

        "oge_demo": {
            "directory": "demo",
            "type": "executable",
            "depends": ["oge_graphics", "oge_audio"]
        }
    }

This project file describes a modular project with 4 modules, three of which are static libraries, and the other is a executable.

When you are using onemake to build the project, it will build libraries and link them with the executable.

Although `oge_demo` doesn't directly depend on `oge_system`, it will also link with it, cos its dependencies referenced them

profiles
--------

Profiles defines how projects are cross compiled. Please refer to `profiles/*` for details.

Command line options
====================

onemake use option=value format to assign options, currently available options are:

* `target_platform`: windows, darwin, linux, openwrt, and etc...
* `target_arch`: i386, `x86_64`, armv7a, mips, mipsel, and etc...
* `scheme`: debug, release
* `concurrent`: max concurrent jobs
* `projects`: projects to build

Some examples:

* only compile `oge_graphics` and its dependencies
    onemake.py projects=oge_graphics

* compile both `oge_graphics` and `oge_audio`
    onemake.py projects=oge_graphics,oge_audio

* compile with 8 parallel jobs
    onemake.py concurrent=8

* cross compile for openwrt with mips ISA:
    export STAGING_DIR=your_open_wrt_staging_dir
    export PATH=$PATH:$STAGING_DIR/toolchain-your_toolchain_name/bin
    onemake.py target_platform=openwrt target_arch=mips

