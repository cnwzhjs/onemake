import thread
import threading
import os.path

ALL_JOBS={}
JOBS_COUNT={
    'pending': 0,
    'working': 0,
    'error': 0,
    'done': 0,
    'source': 0
}
JOBS_LOCK=thread.allocate_lock()
JOBS_COND=threading.Condition()

class Job(object):
    def __init__(self, job_type, dest, depends, args=None):
        self.job_type = job_type
        self.dest = dest
        self.depends = depends
        self.args = args
        self.__status = "pending"

    @property
    def status(self):
        return self.__status

    @status.setter
    def status(self, v):
        if v == self.__status:
            return

        JOBS_COUNT[self.__status] -= 1
        JOBS_COUNT[v] += 1
        self.__status = v

    @property
    def ready_to_start(self):
        if self.__status != 'pending':
            return False

        for depend in self.depends:
            if not depend:
                continue
            if depend.status != 'done':
                return False

        return True

    @property
    def should_compile(self):
        if self.job_type == 'source_library':
            return False
        elif self.depends is None or not len(self.depends):
            return not os.path.exists(self.dest)
        else:
            if not os.path.exists(self.dest):
                return True
            ctime = os.path.getctime(self.dest)
            for depend_job in self.depends:
                if depend_job is None:
                    continue
                if os.path.exists(depend_job.dest) and os.path.getctime(depend_job.dest) > ctime:
                    return True
            return False


def add_job(job_type, dest, depends, args=None):
    if dest in ALL_JOBS:
        return

    job = Job(job_type, dest, depends, args)
    JOBS_COUNT['pending'] += 1
    ALL_JOBS[dest] = job

    return job


def add_source_job(filename):
    job = add_job('source', filename, [])

    if job is not None:
        job.status = 'done'
        JOBS_COUNT['source'] += 1

    return job


def add_or_lookup_source_job(filename):
    return ALL_JOBS[filename] if filename in ALL_JOBS else add_source_job(filename)


def fetch_and_mark_start():
    output = "wait", None
    JOBS_LOCK.acquire()
    if JOBS_COUNT['pending'] == 0 or JOBS_COUNT['error'] != 0:
        output = "done", None
    else:
        for job in ALL_JOBS.values():
            if job.ready_to_start:
                job.status = 'working'
                output = "work", job
                break
    JOBS_LOCK.release()

    if output[0] == "wait":
        JOBS_COND.acquire()
        JOBS_COND.wait()
        JOBS_COND.release()

        return fetch_and_mark_start()
    else:
        return output


def __update_status(job, new_status):
    JOBS_LOCK.acquire()
    job.status = new_status
    JOBS_LOCK.release()

    JOBS_COND.acquire()
    JOBS_COND.notify_all()
    JOBS_COND.release()

def mark_error(job):
    __update_status(job, 'error')


def mark_done(job):
    __update_status(job, 'done')
