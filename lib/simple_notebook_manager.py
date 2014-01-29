"""A simple NotebookManager for IPython

The SimpleNotebookManager in this module is meant to illustrate
the NotebookManager API. It is not useful for any application
because it stores notebooks in memory, making them volatile.

All notebook data is stored in the attribute 'tree', which
is a dictionary mapping paths to dictionaries mapping
names to notebooks.

A notebook is represented by a dictionary with the following keys:

 - 'created': the creation date

 - 'ipynb': a string whose contents are the same as those of
            a notebook file (.ipynb)

 - 'ipynb_last_modified': the date of the last modification
            of the entry 'ipynb'

 - 'py': a string whose contents are the same as those of the
         Python script file (.py)

 - 'py_last_modified': the date of the last modification
         of the entry 'py'

 - 'checkpoints': a list of checkpoints

Each entry of the checkpoint list is a tuple of three elements:

 0: the checkpoint_id (a string)

 1: the modification date of the checkpoint

 2: a copy of notebook['ipynb'] at the time of the checkpoint

"""
import itertools

import copy
from io import StringIO
import os

from tornado import web

from IPython.html.services.notebooks.nbmanager import NotebookManager
from IPython.nbformat import current
from IPython.utils import tz



class SimpleNotebookManager(NotebookManager):

    def info_string(self):
        return "Serving notebooks from memory"

    def __init__(self, **kwargs):
        super(SimpleNotebookManager, self).__init__(**kwargs)
        self.tree = {'': {}}

    # The method get_os_path does not exist in NotebookManager,
    # but must be provided because it is called from 
    # IPython.html.services.sessions.handlers.SessionRootHandler.post.
    # It is not quite clear what this method should return.
    def get_os_path(self, name=None, path=''):
        return os.getcwd()

    def path_exists(self, path):
        """Does the API-style path (directory) actually exist?
        
        Parameters
        ----------
        path : string
            The path to check. This is an API path (`/` separated,
            relative to base notebook-dir).
        
        Returns
        -------
        exists : bool
            Whether the path is indeed a directory.

        Note: The empty path ('') must exist for the server to
              start up properly.
        """
        exists = path in self.tree
        self.log.debug("path_exists('%s') -> %s", path, str(exists))
        return exists

    def notebook_exists(self, name, path=''):
        """Returns a True if the notebook exists. Else, returns False.

        Parameters
        ----------
        name : string
            The name of the notebook you are checking.
        path : string
            The relative path to the notebook (with '/' as separator)

        Returns
        -------
        bool
        """
        assert name.endswith(self.filename_ext)

        exists = self.path_exists(path) and name in self.tree[path]
        self.log.debug("notebook_exists('%s', '%s') -> %s",
                       name, path, str(exists))
        return exists

    def list_notebooks(self, path=''):
        """Return a list of notebook dicts without content.

        This returns a list of dicts, each of the form::

            dict(notebook_id=notebook,name=name)

        This list of dicts should be sorted by name::

            data = sorted(data, key=lambda item: item['name'])
        """
        if self.path_exists(path):
            notebooks = [self.get_notebook_model(name, path, content=False)
                         for name in self.tree[path]]
        else:
            notebooks = []
        notebooks = sorted(notebooks, key=lambda item: item['name'])
        self.log.debug("list_notebooks('%s') -> %s", path, notebooks)
        return notebooks

    def get_notebook_model(self, name, path='', content=True):
        """ Takes a path and name for a notebook and returns its model
        
        Parameters
        ----------
        name : str
            the name of the notebook
        path : str
            the URL path that describes the relative path for
            the notebook
            
        Returns
        -------
        model : dict
            the notebook model. If contents=True, returns the 'contents' 
            dict in the model as well.
        """

        self.log.debug("get_notebook_model('%s', '%s', %s)",
                       name, path, str(content))
        assert name.endswith(self.filename_ext)

        if not self.notebook_exists(name, path):
            raise web.HTTPError(404, u'Notebook does not exist: %s' % name)
        notebook = self.tree[path][name]

        model ={}
        model['name'] = name
        model['path'] = path
        model['created'] = notebook['created']
        model ['last_modified'] = notebook['ipynb_last_modified']
        if content is True:
            with StringIO(notebook['ipynb']) as f:
                model['content'] = current.read(f, u'json')
        self.log.debug("get_notebook_model -> %s", str(model))
        return model

    # NotebookManager.create_notebook_model is a complete
    # working implementation. It is overridden here only
    # to add logging for debugging.
    # Note however that increment_filename must be reimplemented
    # because the version in NotebookManager has a bug.
    def create_notebook_model(self, model=None, path=''):
        """Create a new notebook and return its model with no content."""
        new_model = super(SimpleNotebookManager, self) \
                         .create_notebook_model(model, path)
        self.log.debug("create_notebook_model(%s, '%s') -> %s",
                       str(model), path, str(new_model))
        return new_model

    def increment_filename(self, basename, path=''):
        """Increment a notebook name to make it unique.

        Parameters
        ----------
        basename : unicode
            The base name of a notebook (no extension .ipynb)
        path : unicode
            The URL path of the notebooks directory

        Returns
        -------
        filename : unicode
            The complete filename (with extension .ipynb) for
            a new notebook, guaranteed not to exist yet.
        """
        self.log.debug("increment_filename('%s', '%s')",
                       str(basename), str(path))
        assert self.path_exists(path)

        notebooks = self.tree[path]
        for i in itertools.count():
            name = u'{basename}{i}'.format(basename=basename, i=i)
            if name not in notebooks:
                break
        name = name + self.filename_ext
        self.log.debug("increment_filename -> '%s'", str(name))
        return name

    def save_notebook_model(self, model, name, path=''):
        """Save the notebook model and return the model with no content."""

        self.log.debug("save_notebook_model(%s, '%s', '%s')",
                       model, str(name), str(path))
        assert name.endswith(self.filename_ext)

        if 'content' not in model:
            raise web.HTTPError(400, u'No notebook JSON data provided')
        
        # One checkpoint should always exist
        if self.notebook_exists(name, path) \
           and not self.list_checkpoints(name, path):
            self.create_checkpoint(name, path)

        new_path = model.get('path', path)
        new_name = model.get('name', name)

        if path != new_path or name != new_name:
            self.rename_notebook(name, path, new_name, new_path)

        # Create the path and notebook entries if necessary
        if new_path not in self.tree:
            self.tree[new_path] = {}
        if new_name not in self.tree[new_path]:
            self.tree[new_path][new_name] = \
                   dict(created = tz.utcnow(), checkpoints=[])
        notebook = self.tree[new_path][new_name]

        # Save the notebook file
        nb = current.to_notebook_json(model['content'])
        if 'name' in nb['metadata']:
            nb['metadata']['name'] = u''
        ipynb_stream = StringIO()
        current.write(nb, ipynb_stream, u'json')
        notebook['ipynb'] = ipynb_stream.getvalue()
        notebook['ipynb_last_modified'] = tz.utcnow()
        ipynb_stream.close()

        # Save .py script as well
        py_stream = StringIO()
        current.write(nb, py_stream, u'json')
        notebook['py'] = py_stream.getvalue()
        notebook['py_last_modified'] = tz.utcnow()
        py_stream.close()

        # Return model
        model = self.get_notebook_model(new_name, new_path, content=False)
        self.log.debug("save_notebook_model -> %s", model)
        return model

    def rename_notebook(self, name, path, new_name, new_path):
        """Rename a notebook."""
        self.log.debug("rename_notebook('%s', '%s', '%s', '%s')",
                       name, path, new_name, new_path)
        assert name.endswith(self.filename_ext)
        assert new_name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        notebook = self.tree[path][name]
        if new_path not in self.tree:
            self.tree[new_path] = {}
        self.tree[new_path][new_name] = notebook
        self.delete_notebook_model(name, path)

    def delete_notebook_model(self, name, path=''):
        """Delete notebook by name and path."""
        self.log.debug("delete_notebook_model('%s', '%s')",
                       str(name), str(path))
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        del self.tree[path][name]
        if len(self.tree[path]) == 0:
            del self.tree[path]

    # Note: I don't understand why this method is needed,
    # nor under which circumstances it is called.
    def update_notebook_model(self, model, name, path=''):
        """Update the notebook's path and/or name"""
        self.log.debug("upate_notebook_model(%s, '%s', '%s')",
                       str(model), name, path)
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        new_name = model.get('name', name)
        new_path = model.get('path', path)
        if path != new_path or name != new_name:
            self.rename_notebook(name, path, new_name, new_path)
        model = self.get_notebook_model(new_name, new_path, content=False)
        self.log.debug("upate_notebook_model -> %s", str(model))
        return model

    def create_checkpoint(self, name, path=''):
        """Create a checkpoint of the current state of a notebook

        Returns a checkpoint_id for the new checkpoint.
        """
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        notebook = self.tree[path][name]
        checkpoint_id = "checkpoint-%d" % (len(notebook['checkpoints'])+1)
        last_modified = notebook['ipynb_last_modified']
        notebook['checkpoints'].append((checkpoint_id,
                                        last_modified,
                                        notebook['ipynb']))
        return dict(id=checkpoint_id, last_modified=last_modified)

    def list_checkpoints(self, name, path=''):
        """Return a list of checkpoints for a given notebook"""
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        checkpoints = self.tree[path][name]['checkpoints']
        checkpoint_info = [dict(id=checkpoint_id, last_modified=last_modified)
                           for checkpoint_id, last_modified, _ in checkpoints]
        self.log.debug("list_checkpoints('%s', '%s') -> %s",
                       name, path, str(checkpoint_info))
        return checkpoint_info

    def restore_checkpoint(self, checkpoint_id, name, path=''):
        """Restore a notebook from one of its checkpoints"""
        self.log.debug("restore_checkpoints(%s,'%s', '%s')",
                       repr(checkpoint_id), name, path)
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        notebook = self.tree[path][name]
        checkpoints = self.tree[path][name]['checkpoints']
        for id, last_modified, ipynb in checkpoints:
            if id == checkpoint_id:
                # this must succeed since the checkpoint_id
                # passed in comes from calling list_checkpoints
                break
        notebook['ipynb_last_modified'] = last_modified
        notebook['ipynb'] = ipynb

    # There doesn't seem to be a way to actually delete a
    # checkpoint through the notebook interface.
    def delete_checkpoint(self, checkpoint_id, name, path=''):
        """delete a checkpoint for a notebook"""
        self.log.debug("delete_checkpoints(%s,'%s', '%s')",
                       repr(checkpoint_id), name, path)
        assert name.endswith(self.filename_ext)
        assert self.notebook_exists(name, path)

        notebook = self.tree[path][name]
        checkpoints = self.tree[path][name]['checkpoints']
        for i in range(len(checkpoints)):
            if checkpoints[i][0] == checkpoint_id:
                # this must succeed since the checkpoint_id
                # passed in comes from calling list_checkpoints
                break
        del checkpoints[i]
