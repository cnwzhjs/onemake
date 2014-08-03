import os.path
import thread
import console_helper

MKDIR_LOCK=thread.allocate_lock()

def get_ext_filename(filename):
    if not '.' in filename:
        return ''
    else:
        return filename[filename.rfind('.')+1:]


def get_obj_filename(filename):
    ext = get_ext_filename(filename)
    return filename[0:len(filename)-len(ext)] + 'o'


def mk_indent(indent):
    output = ''

    for i in xrange(indent):
        output += '  '

    return output

def mkdir_if_not_exist(path, indent=1):
    if path.endswith('/'):
        path = path[0:len(path) - 1]

    MKDIR_LOCK.acquire()
    if os.path.exists(path):
        MKDIR_LOCK.release()
        return
    MKDIR_LOCK.release()

    dir_path = dirname(path)

    if dir_path == path:
        return

    mkdir_if_not_exist(dir_path, indent + 1)

    MKDIR_LOCK.acquire()
    if not os.path.exists(path):
        os.mkdir(path)
    MKDIR_LOCK.release()

def dirname(path):
    if not path:
        return path

    if '/' not in path:
        return path

    p = path.rfind('/')

    return path[0:p]
