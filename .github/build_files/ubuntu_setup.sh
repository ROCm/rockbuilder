sudo apt update
sudo apt install -y gfortran git git-lfs ninja-build cmake g++ pkg-config xxd patchelf automake libtool python-is-python3 python3-venv python3-dev python3-pip libegl1-mesa-dev
sudo apt upgrade

git config --global user.email "rockbuilder@amd.com"
git config --global user.name "rockbuilder"
