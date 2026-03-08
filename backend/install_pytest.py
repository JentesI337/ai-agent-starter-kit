import sys
import subprocess

def install_pytest():
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pytest'])
        print('pytest installed successfully')
    except subprocess.CalledProcessError as e:
        print(f'Failed to install pytest: {e}')

if __name__ == '__main__':
    install_pytest()
