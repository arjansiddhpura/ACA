#!/bin/bash
#SBATCH --partition=exercise-eml
#SBATCH --gres=gpu:1
#SBATCH --time=00:05:00
#SBATCH --output=slurm_output.txt
#SBATCH --error=slurm_error.txt

./hello_world


