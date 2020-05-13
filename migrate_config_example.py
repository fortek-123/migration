# Make a copy of this file and call it migrate_config.py in the same directory and modify it
# according the instructions by each attributes.
#

# The source located in Stash/Bitbucket
#
source = {
    # Bitbucket user with access to projectSlugs
    "username": "my_username",
    # Create a personal access token at Profile -> Account -> Personal Access Token with Read permissions
    "apiKey": "...",  # None - prompt for password
    "host": "bitbucket-sed.broadcom.net",
    # Users personal repositories under the user name. Make sure to start with ~ (tilde)
    # "userSlugs": [
    #     "~ab123456"
    # ],
    # The projects that contain the repositories to clone, this uses the project slug/key
    "projectSlugs": [
        "SLUG",
    ],
    # All repositories are cloned by default, to specify to limit which repos are
    # mirrored, provide a list of the repository slugs per project slug.
    "repoSlugs": {
        # "~ab123456": [
        #     "only-this-repo-name"
        # ],
        # "SLUG": [
        #     "only-this-repo-name"
        # ]
    }
}

# To prevent certain repositories from being clone or pushed, add the repository name or regex 
# pattern below.
#
ignore = {
    "repos": {
        "SLUG": [
            "ignored-repo",
        ]
    },
    "patterns": {
        "CYN": [
            "^ignore-",
        ]
    },
    "forkedReposInUser": False  # If True all forked repositories in user personal space from Projects will be ignored
}

mirror = {
    # Local directory to store base git repos pull from the source
    "location": "/Users/myuser/RepoSync"
}

# The repositories will have the destination named as <team prefix>-<project name>-<repo name>
# Repo names will be normalised to prevent double prefixing by default.
# e.g. A project name of 'myproject' and source repo name of 'myproject-cat' will stay 'myproject-cat'
#      but a repo name of 'cat-repo' will become 'myproject-cat-repo'
destination = {
    # Team admins okta ID
    "username": "ab12345",
    # Generate an GitHub application specific key with the scopes of 'repo' and 'org:admin'
    # Settings -> Developer settings -> Personal access tokens -> Generate new token
    "apiKey": "...",
    "host": "github.gwd.broadcom.net",
    # The organisation to create repositories in
    "orgName": "SED",
    # The prefix required for your team
    "teamPrefix": "TEAM_PREFIX",
    # The team assigned at creation time of a repository
    "teamOwner": "TEAM_PREFIX_Owners",
    # All repos that are pushed have permissions assigned to the teams in this mapping.
    "repoAccess": {
        "admin": "TEAM_PREFIX_Owners",
        "push": "TEAM_PREFIX_Integrators",
        "pull": "TEAM_PREFIX_Developers"
    },
    # If True, the permissions are only set during repository creation time, if False then set on every run.
    "skipPermissionsIfRepoExists": True,
    # Disable project name prefixing
    "useProjectPrefix": True,
    # The project name is the project slug by default, to change this add a mapping from
    # slug to name to use for remote repo naming.
    "projectSlugMappings": {
        "SLUG": "my-project",

    },
    # When generating the repository name an duplicate may occur if taking repositories from many
    # BitBucket projects, use this to specify an alternative name.  Note that project name prefixing
    # does not happen, the name is used as is.
    "repoNameMapping": {
        "SLUG": {
            "my-overlapping-name": "my-remapped-name"
        }
    }
}
