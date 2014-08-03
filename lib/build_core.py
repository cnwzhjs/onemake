import os.path
import platform
import console_helper
import path_helper
import job_manager

PROJECTS={}
ENV={}

ROOT=os.path.realpath(path_helper.dirname(os.path.realpath(__file__)) + '/../..')
SCHEME='debug'
TARGET=platform.uname()[4]
PROFILE=platform.uname()[0].lower()

BUILD_ROOT=ROOT + '/build/{0}-{1}-{2}'.format(PROFILE, TARGET, SCHEME)
OBJECT_ROOT=BUILD_ROOT + '/object'
OUTPUT_ROOT=BUILD_ROOT + '/output'

def config(scheme=None, target=None, profile=None):
    global SCHEME, TARGET, PROFILE
    global BUILD_ROOT, OBJECT_ROOT, OUTPUT_ROOT

    if scheme is not None:
        SCHEME = scheme

    if target is not None:
        TARGET=target

    if profile is not None:
        PROFILE=profile

    BUILD_ROOT=ROOT + '/build/{0}-{1}-{2}'.format(PROFILE, TARGET, SCHEME)
    OBJECT_ROOT=BUILD_ROOT + '/object'
    OUTPUT_ROOT=BUILD_ROOT + '/output'


def scan_project_depends(name, project):
    if 'all_depends' in project:
        return

    project_include_dir = project["directory"] + "/include"
    project_internal_include_dir = project["directory"] + "/internal_include"

    include_dirs = []

    if os.path.exists(project_include_dir):
        include_dirs.append(project_include_dir)

    if os.path.exists(project_internal_include_dir):
        include_dirs.append(project_internal_include_dir)

    include_dirs.append(OUTPUT_ROOT + '/include')

    if 'extra_include_dirs' in project:
        for extra_include_dir in project['extra_include_dirs']:
            include_dir = extra_include_dir.replace('${OUTPUT_ROOT}', OUTPUT_ROOT)
            include_dir = include_dir.replace('${SRC_DIR}', project['directory'])
            include_dir = include_dir.replace('${OBJECT_ROOT}', OBJECT_ROOT)
            include_dirs.append(include_dir)

    all_depends = project['depends'] if 'depends' in project else []

    if 'depends' in project:
        for depend in project['depends']:
            if depend not in PROJECTS:
                console_helper.fatal("failed to find dependency {0} used by {1}".format(depend, name))
            scan_project_depends(depend, PROJECTS[depend])

            for include_dir in PROJECTS[depend]["include_dirs"]:
                if include_dir not in include_dirs and not include_dir.endswith('internal_include'):
                    include_dirs.append(include_dir)

            for indirect_depend in PROJECTS[depend]["all_depends"]:
                if indirect_depend not in all_depends:
                    all_depends.append(indirect_depend)

    if 'include_dirs' not in project:
        project['include_dirs'] = include_dirs

    project['all_depends'] = all_depends


def is_excluded(project, filename):
    src_directory = project["directory"] + "/src"
    relative_path = filename[len(src_directory) + 1:]
    exclude_src_dirs = project.get('exclude_src_dirs', [])
    exclude_src_files = project.get('exclude_src_files', [])

    if relative_path in exclude_src_files:
        return True

    for dir in exclude_src_dirs:
        if relative_path.startswith(dir + '/'):
            return True

    return False

def scan_source_files(name, project):
    if 'source_files' in project or 'custom_build' in project:
        return

    source_files = []
    def process_dir(_, base_path, files):
        for filename in files:
            path = base_path + '/' + filename
            if os.path.isdir(path):
                continue
            if is_excluded(project, path):
                continue
            ext = path_helper.get_ext_filename(filename)
            if ext not in ['c', 'cc', 'cpp']:
                continue
            source_files.append(path)
    
    src_dirs = project.get('src_dirs', ['src'])
    for src_dir_name in src_dirs:
        src_directory = project["directory"] + "/" + src_dir_name
        os.path.walk(src_directory, process_dir, None)

    project['source_files'] = source_files


def process_flag(flag):
    has_space = ' ' in flag
    has_double_quote = '"' in flag
    has_single_quote = "'" in flag

    if not has_space and not has_double_quote and not has_single_quote:
        return flag
    elif not has_single_quote:
        return "'" + flag + "'"
    elif not has_double_quote:
        return '"' + flag + '"'
    else:
        return flag.replace('\\', '\\\\').replace(' ', '\\ ').replace('"', '\\"').replace("'", "\\'")

def concat_flags(flags):
    return ' '.join(map(process_flag, flags))

def add_compiler_flag(flags, compiler, option, value):
    for flag in ENV['compiler_options'][compiler][option]:
        flags.append(flag.format(value))

def generate_compiler_flags(project, compiler_name, flag_name, options, extra_flags=None):
    if flag_name in project:
        return

    flags = []
    if extra_flags:
        for extra_flag_name, extra_flag_value in extra_flags:
            add_compiler_flag(flags, compiler_name, extra_flag_name, extra_flag_value)

    for enum_option_name, option_name in options:
        for option in project.get(enum_option_name, []):
            if enum_option_name == 'all_depends' and PROJECTS[option]['job'].job_type == 'source_library':
                continue
            add_compiler_flag(flags, compiler_name, option_name, option)
    if 'env' in project and flag_name in project['env']:
        flags.extend(project['env'][flag_name])

    project[flag_name] = flags

def generate_flags(name, project):
    generate_compiler_flags(project, "cc", "cflags", [("include_dirs", 'include_dir')])
    generate_compiler_flags(project, "cxx", "cxxflags", [("include_dirs", 'include_dir')])

def create_jobs(name, project):
    if 'job' in project:
        return

    depends_jobs = []
    if 'depends' in project:
        for depend in project['depends']:
            create_jobs(depend, PROJECTS[depend])
            depends_jobs.append(PROJECTS[depend]['job'])

    if project['type'] == 'library':
        project["output"] = '{0}/lib/lib{1}.a'.format(OUTPUT_ROOT, name)
        project["log_file"] = '{0}/lib/lib{1}.a.log'.format(OBJECT_ROOT, name)
    else:
        project["output"] = '{0}/bin/{1}'.format(OUTPUT_ROOT, name)
        project["log_file"] = '{0}/bin/{1}.log'.format(OBJECT_ROOT, name)

    job_depends = []
    if 'source_files' in project:
        obj_files = []
        for src in project["source_files"]:
            src_path = ROOT + '/' + src
            dest_path = OBJECT_ROOT + '/' + path_helper.get_obj_filename(src)
            source_job = job_manager.add_or_lookup_source_job(src_path)
            compile_job_depends = [source_job]
            compile_job_depends.extend(depends_jobs)
            compile_job = job_manager.add_job("compile", dest_path, compile_job_depends, name)
            job_depends.append(compile_job)
            obj_files.append(dest_path)
        project['object_files'] = obj_files

    if project.get('output_headers', False):
        include_directory = project["directory"] + '/include'
        def process_dir(_, base_path, files):
            for filename in files:
                path = base_path + '/' + filename
                if os.path.isdir(path):
                    continue
                relative_path = path[len(include_directory) + 1:]
                dest_path = OUTPUT_ROOT + '/include/' + relative_path

                source_job = job_manager.add_or_lookup_source_job(path)
                copy_job_depends = [source_job]
                copy_job_depends.extend(depends_jobs)
                copy_job = job_manager.add_job("copy", dest_path, copy_job_depends, path)
                job_depends.append(copy_job)

        os.path.walk(include_directory, process_dir, None)
    
    job_depends.extend(depends_jobs)

    if 'custom_build' in project:
        job = job_manager.add_job('custom_build', project['output'], job_depends, project)
    elif project['type'] == 'library':
        if project.get('source_files', []):
            job = job_manager.add_job('static_library', project['output'], job_depends, project)
        else:
            job = job_manager.add_job('source_library', name, job_depends, project)
    else:
        job = job_manager.add_job('executable', project['output'], job_depends, project)

    project['job'] = job


def prepare():
    for name, project in PROJECTS.items():
        scan_project_depends(name, project)
        scan_source_files(name, project)
        generate_flags(name, project)
    for name, project in PROJECTS.items():
        create_jobs(name, project)
    for name, project in PROJECTS.items():
        generate_compiler_flags(project, "ld", "ldflags", [("all_depends", 'library'), ("external_depends", "library"), ("library_dirs", "library_dir")], [("library_dir", OUTPUT_ROOT + "/lib")])
