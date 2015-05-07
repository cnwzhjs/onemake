import sys
import platform

OPTIONS={
    'concurrent': '1',
    'operation': 'build',
    'scheme': 'debug',
    'target': 'generic',
    'host_arch': platform.uname()[4],
    'host_platform': platform.uname()[0].lower()
}

OPTIONS['target_arch'] = OPTIONS['host_arch']
OPTIONS['target_platform'] = OPTIONS['host_platform']

for i in xrange(1, len(sys.argv)):
    arg = sys.argv[i]

    if '=' in arg:
        fields = arg.split('=', 1)
        OPTIONS[fields[0]] = fields[1]
    else:
        OPTIONS[arg] = 'yes'
