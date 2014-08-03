#! /usr/bin/python

import os
import os.path
import sys
import thread
import threading

ROOT=os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ALL_ERRORS=[]
ALL_ERRORS_LOCK=thread.allocate_lock()

sys.path.append(ROOT + "/scripts/lib")

import build_core
import job_manager
import console_helper
import path_helper

build_core.PROJECTS={
    'acsystem': {
        "directory": "common/libacsystem",
        "type": "library"
    },

    'acprotocol': {
        "directory": "common/libacprotocol",
        "type": "library",
        "depends": ["acsystem"]
    },

    'acclient': {
        "directory": "common/libacclient",
        "type": "library",
        "depends": ["acprotocol"]
    },

    'douwan_acd': {
        "directory": "server",
        "type": "executable",
        "depends": ["acprotocol", "cpprest"],
        "env": {
            "ldflags": "-lboost_system -lboost_thread"
        }
    },

    'cpprest': {
        'directory': "server/deps/cpprest/Release",
        'type': "library",
        'custom_build': "cmake",
        'cmake_flags': '-DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF',
        'make_flags': '-j4',
        'custom_build_output_files': 'Binaries/libcpprest.a*'
    }
}

build_core.config(scheme="debug")
build_core.prepare()


def run_cmd(cmd, log_file):
    path_helper.mkdir_if_not_exist(os.path.dirname(log_file))

    if os.system(cmd + " > {0} 2>&1".format(log_file)):
        ALL_ERRORS_LOCK.acquire()
        ALL_ERRORS.append([
            "Failed to execute following command:",
            cmd,
            "Please refer to log {1}: ".format(cmd, log_file)
        ])
        ALL_ERRORS_LOCK.release()
        return False
    else:
        return True


def compile_file(project_name, src, dest):
    project = build_core.PROJECTS[project_name]
    ext = path_helper.get_ext_filename(src)

    if ext == 'c':
        return run_cmd("gcc -o {0} -c {1} -std=c99 -g -Wall -I{3}/include {2}".format(dest, src, project["cflags"], build_core.OUTPUT_ROOT), dest + '.log')
    elif ext in ('cc', 'cpp'):
        return run_cmd("g++ -o {0} -c {1} -std=c++11 -g -Wall -I{3}/include {2}".format(dest, src, project["cxxflags"], build_core.OUTPUT_ROOT), dest + '.log')


def custom_build(dest, project):
    src_dir = build_core.ROOT + '/' + project['directory']
    object_dir = build_core.OBJECT_ROOT + '/' + project['directory']

    path_helper.mkdir_if_not_exist(object_dir)

    if project['custom_build'] == 'cmake':
        cmake_flags = project['cmake_flags'] if 'cmake_flags' in project else ''
        make_flags = project['make_flags'] if 'make_flags' in project else ''

        if not run_cmd('cd {0} && cmake {1} {2}'.format(object_dir, src_dir, cmake_flags), project['log_file'] + '.cmake'):
            return False

        if not run_cmd('cd {0} && make {1}'.format(object_dir, make_flags), project['log_file'] + '.make'):
            return False

        return run_cmd('cp {0}/{1} {2}'.format(object_dir, project['custom_build_output_files'], os.path.dirname(dest)), project['log_file'] + '.copy')
    elif project['custom_build'] == 'configure_make':
        configure_flags = project['configure_flags'] if 'configure_flags' in project else ''
        make_flags = project['make_flags'] if 'make_flags' in project else ''

        if not run_cmd('cd {0} && {1}/configure --prefix={2} {3}'.format(object_dir, src_dir, build_core.OUTPUT_ROOT, configure_flags), project['log_file'] + '.configure'):
            return False
        if not run_cmd('cd {0} && make {1}'.format(object_dir, make_flags), project['log_file'] + '.make'):
            return False
        return run_cmd('cd {0} && make install'.format(object_dir), project['log_file'] + '.make')

def worker(thread_id):
    while True:
        result, job = job_manager.fetch_and_mark_start()
        if result == 'done':
            break
        if job:
            job_manager.JOBS_LOCK.acquire()
            jobs_done = job_manager.JOBS_COUNT['done']
            jobs_working = job_manager.JOBS_COUNT['working']
            jobs_source = job_manager.JOBS_COUNT['source']
            jobs_pending = job_manager.JOBS_COUNT['pending']
            job_manager.JOBS_LOCK.release()

            dest_dir = os.path.dirname(job.dest)
            path_helper.mkdir_if_not_exist(dest_dir)

            succeed = False

            if job.should_compile:
                console_helper.echo_info("[{0}/{1}] [{2}] {3}...".format(jobs_done + jobs_working - jobs_source, jobs_done + jobs_working + jobs_pending - jobs_source, job.job_type, job.dest[len(build_core.BUILD_ROOT)+1:]))
                if job.job_type == 'compile':
                    succeed = compile_file(job.args, job.depends[0].dest, job.dest)
                elif job.job_type == 'static_library':
                    succeed = run_cmd('ar crv {0} {1}'.format(job.dest, build_core.concat_flags(job.args['object_files'])), job.args['log_file'])
                elif job.job_type == "executable":
                    succeed = run_cmd('g++ -o {0} {1} -pthread -L{2} {3}'.format(job.dest, build_core.concat_flags(job.args['object_files']), build_core.OUTPUT_ROOT + '/lib', job.args['ldflags']), job.args['log_file'])
                elif job.job_type == "script":
                    succeed = run_cmd(build_core.concat_flags(["cd", build_core.ROOT]) + " && " + job.args, job.args['log_file'])
                elif job.job_type == "custom_build":
                    succeed = custom_build(job.dest, job.args)
            else:
                succeed = True

            if succeed:
                job_manager.mark_done(job)
            else:
                job_manager.mark_error(job)

threads=[]

for i in xrange(4):
    worker_thread = threading.Thread(None, worker, args=(i,))
    worker_thread.start()
    threads.append(worker_thread)

for worker_thread in threads:
    if not worker_thread.is_alive():
        continue
    worker_thread.join()

if job_manager.JOBS_COUNT['error']:
    console_helper.echo_error("{0} errors occurred".format(job_manager.JOBS_COUNT['error']))
    for i in xrange(len(ALL_ERRORS)):
        error_entry = ALL_ERRORS[i]
        console_helper.echo_error("Error {0}".format(i))
        for line in error_entry:
            console_helper.echo_warn("    {0}".format(line))
    exit(1)
else:
    console_helper.echo_info("all done")
