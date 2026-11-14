import subprocess


def run(request):
    return subprocess.run("nslookup " + request.args["host"], shell=True).stdout