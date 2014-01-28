import itertools

from io import StringIO

from tornado import web

from IPython.html.services.notebooks.nbmanager import NotebookManager
from IPython.nbformat import current
from IPython.utils import tz


class SimpleNotebookManager(NotebookManager):

    # First part: the NotebookManager API
    # These methods are required by IPython

    def info_string(self):
        return "Serving notebooks from memory"

    def __init__(self, **kwargs):
        super(SimpleNotebookManager, self).__init__(**kwargs)
        self.tree = {}

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
        """
        return path in self.tree

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
        return self.path_exists(path) and name in self.tree[path]

    def list_notebooks(self, path=''):
        """Return a list of notebook dicts without content.

        This returns a list of dicts, each of the form::

            dict(notebook_id=notebook,name=name)

        This list of dicts should be sorted by name::

            data = sorted(data, key=lambda item: item['name'])
        """
        if self.path_exists(path):
            notebooks = [self.get_notebook_model(name, path, content=False)
                         for name in self.tre[path]]
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

        if not self.notebook_exists(name, path):
            raise web.HTTPError(404, u'Notebook does not exist: %s' % name)
        notebook = self.tree[path][name]

        model ={}
        model['name'] = name
        model['path'] = path
        model['created'] = notebook['created']
        model ['last_modified'] = notebook['ipynb_last_modified']
        if content is True:
            model['content'] = notebook['ipynb']
        return model

    def create_notebook_model(self, model=None, path=''):
        """Create a new notebook and return its model with no content."""
        if model is None:
            now = tz.utcnow()
            model = {'created': now,
                     'last_modified': now}
        if 'name' not in model:
            model['name'] = self._increment_filename('Untitled', path)
        if 'content' not in model:
            metadata = current.new_metadata(name=u'')
            model['content'] = current.new_notebook(metadata=metadata)

        model['path'] = path
        model = self.save_notebook_model(model, model['name'], model['path'])
        return model

    def save_notebook_model(self, model, name, path=''):
        """Save the notebook model and return the model with no content."""

        if 'content' not in model:
            raise web.HTTPError(400, u'No notebook JSON data provided')
        
        new_path = model.get('path', path)
        new_name = model.get('name', name)

        if path != new_path or name != new_name:
            self.rename_notebook(name, path, new_name, new_path)

        # Create the path and notebook entries if necessary
        if new_path not in self.tree:
            self.tree[new_path] = {}
        if new_name not in self.tree[new_path]:
            self.tree[new_path][new_name] = {'created': tz.utcnow()}
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
        current.write(nb, ipynb_stream, u'json')
        notebook['py'] = py_stream.getvalue()
        notebook['py_last_modified'] = tz.utcnow()
        py_stream.close()

        # Return model
        model = self.get_notebook_model(new_name, new_path, content=False)
        return model

    def rename_notebook(self, name, path, new_name, new_path):
        """Rename a notebook."""
        assert self.notebook_exists(name, path)
        notebook = self.tree[path][name]
        if new_path not in self.tree:
            self.tree[new_path] = {}
        self.tree[new_path][new_name] = notebook
        self.delete_notebook_model(name, path)

    def delete_notebook_model(self, name, path=''):
        """Delete notebook by name and path."""
        assert self.notebook_exists(name, path)
        del self.tree[path][name]
        if len(self.tree[path]) == 0:
            del self.tree[path]

    # Second part: implementation details
    # These methods are used in the implementation of
    # SimpleNotebookManager, but are not called from elseehere.

    def _increment_filename(self, basename, path=''):
        """Increment a notebook name to make it unique.
        
        Parameters
        ----------
        basename : unicode
            The name of a notebook
        path : unicode
            The URL path of the notebooks directory
        """
        assert self.path_exists(path)
        notebooks = self.tree[path]
        for i in itertools.count():
            name = u'{basename}{i}'.format(basename=basename, i=i)
            if name not in notebooks:
                break
        return name


