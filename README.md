# BitBucket to GitHub Migration Script

## Summary

This script migrates BitBucket repositories to GitHub.  It applies the naming conventions required for Broadcom usage.  It is able to move incremental changes from BitBucket to GitHub.


## Requirements

This script requires Python 3.  It has only been tested v3.7 on macOS Catalina.

## Usage

One command:

    $ ./run.sh --mode=<mode>

Manually run inside Python virtual environment:

    $ python3 -m venv env
    $ . env/bin/activate
    $ pip install -r requirements.txt
    $ python3 migrate_repos.py --mode=<mode>

The scripts has 3 operating modes which are specified using the option `--mode`:

1. **clone**
    This mode will clone all the repositories that can be located to a local directory.  Repositories that already exist on the local drive are skipped.
2. **clone_update**
    This clones any repositories that cannot be located locally and performs an update on all existing repositories to pull any new changes.
3. **push**
    Push the repositories that are in the local directory to GitHub.  This will:
    * Create repositories in GitHub that do not exist or update existing repositories.
    * Set the team permissions for pull, push and admin of each repository.

A typical workflow will be:

    $ ./run.sh --mode=clone_update
    $ ./run.sh --mode=push

## Configuration

Please refer to the `migrate_config_example.py` for an explanation of all the options needing to be set.  The script requires the configuration to be call `migrate_config.py`, Copying the example to this location and customise to your requirements.

It can also migrate users personal repositories from Bitbucket to Github as well, but No naming convention or permissions are applied on personal repositories,
they are migrated as is, into personal space of the user doing the migration at github.

To migrate your repositories, create an apiKey in both Bitbucket and Github in your account and add the username in the `userSlugs` configuration.


## Known Issues

In some cases the push will fail when updating .  The error message isn't visible (but can be seen by doing `git push --mirror target` in the affected git repository).  This is usually related to the following:

    GH003: Sorry, force-pushing to refs/pull-requests/<number>/merge is not allowed.

The simplest solution is to delete the repository in GitHub and have the script recreate and push it again.

## Contact

The script was written by Mark Broadbent <mark.broadbent@broadcom.com>
