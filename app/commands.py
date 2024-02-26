from app import db
import click
from os import system
from datetime import datetime

@click.group()
def dbdump():
    """Perform a mysqldump command for this app."""
    pass

@dbdump.command()
@click.option('-d', '--directory', default=None, help='Directory to put archive')
def archive(directory):
    directory = directory + '/' if directory else ''
    fname = '{}db-dump-{}.sql'.format(directory, datetime.now().strftime('%B_%d_%Y_%s'))
    tables = [a for a in db.metadata.tables.keys()]
    print('Dumping tables: {}'.format(tables))
    comstr = 'mysqldump -u root -p quiz {} alembic_version > {}'.format(' '.join(tables), fname)
    if system(comstr):
        print('Failed to dump database')
    else:
        print('Created file {}'.format(fname))
        
