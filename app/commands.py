import click
from os import system
from datetime import datetime

@click.group()
def dbdump():
    """Perform a mysqldump command for this app."""
    pass

@dbdump.command()
def archive():
    pass
    fname = 'db-dump-{}.sql'.format(datetime.now().strftime('%B_%d_%Y_%s'))
    comstr = 'mysqldump -u root -p quiz vproblem vquiz vproblem_vquiz user cproblem cquiz alembic_version > {}'.format(fname)
    try:
        system(comstr)
        print('Created file {}'.format(fname))
    except Exception as e:
        print('Failed to dump database: {}'.format(e))
        
