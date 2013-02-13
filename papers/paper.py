import os
import unicodedata
import re

from pybtex.database import Entry, BibliographyData

import files


DEFAULT_TYPE = 'article'

CONTROL_CHARS = ''.join(map(unichr, range(0, 32) + range(127, 160)))
CITEKEY_FORBIDDEN_CHARS = '@\'\\,#}{~%/'  # '/' is OK for bibtex but forbidden
# here since we transform citekeys into filenames
CITEKEY_EXCLUDE_RE = re.compile('[%s]'
        % re.escape(CONTROL_CHARS + CITEKEY_FORBIDDEN_CHARS))

BASE_META = {
    'filename': None,
    'extension': None,
    'path': None,
    'notes': []
    }


def str2citekey(s):
    key = unicodedata.normalize('NFKD', unicode(s)).encode('ascii', 'ignore')
    key = CITEKEY_EXCLUDE_RE.sub('', key)
    # Normalize chars and remove non-ascii
    return key


class NoDocumentFile(Exception):
    pass


class Paper(object):
    """Paper class. The object is responsible for the integrity of its own
    data, and for loading and writing it to disc.

    The object uses a pybtex.database.BibliographyData object to store
    biblography data and an additional dictionary to store meta data.
    """

    def __init__(self, bibentry=None, metadata=None, citekey=None):
        if not bibentry:
            bibentry = Entry(DEFAULT_TYPE)
        self.bibentry = bibentry
        if not metadata:
            metadata = Paper.create_meta()
        self.metadata = metadata
        # TODO This is not the right way to test that (17/12/2012)
        if unicode(citekey) != str2citekey(citekey):
            raise(ValueError("Invalid citekey: %s" % citekey))
        self.citekey = citekey

    def __eq__(self, other):
        return (type(other) is Paper
            and self.bibentry == other.bibentry
            and self.metadata == other.metadata
            and self.citekey == other.citekey)

    def __repr__(self):
        return 'Paper(%s, %s, %s)' % (
                self.citekey, self.bibentry, self.metadata)

    def __str__(self):
        return self.__repr__()

    # TODO add mechanism to verify keys (15/12/2012)

    def has_file(self):
        """Whether there exist a document file for this entry.
        """
        return self.metadata['path'] is not None

    def get_file_path(self):
        if self.has_file():
            return self.metadata['path']
        else:
            raise NoDocumentFile

    def check_file(self):
        path = self.get_file_path()
        return os.path.exists(path) and os.path.isfile(path)

    def generate_citekey(self):
        """Generate a citekey from bib_data.

        Raises:
            KeyError if no author nor editor is defined.
        """
        author_key = 'author'
        if not 'author' in self.bibentry.persons:
            author_key = 'editor'
        try:
            first_author = self.bibentry.persons[author_key][0]
        except KeyError:
            raise(ValueError(
                    'No author or editor defined: cannot generate a citekey.'))
        try:
            year = self.bibentry.fields['year']
        except KeyError:
            year = ''
        citekey = u'{}{}'.format(u''.join(first_author.last()), year)
        return str2citekey(citekey)

    def set_document(self, docpath):
        fullpdfpath = os.path.abspath(docpath)
        files.check_file(fullpdfpath)
        name, ext = files.name_from_path(docpath)
        self.metadata['filename'] = name
        self.metadata['extension'] = ext
        self.metadata['path'] = fullpdfpath

    def save_to_disc(self, bib_filepath, meta_filepath):
        """Creates a BibliographyData object containing a single entry and
        saves it to disc.
        """
        if self.citekey is None:
            raise(ValueError(
                'No valid citekey initialized. Cannot save paper'))
        bibdata = BibliographyData(entries={self.citekey: self.bibentry})
        files.save_bibdata(bibdata, bib_filepath)
        files.save_meta(self.metadata, meta_filepath)

    def get_document_file_from_bibdata(self, remove=False):
        """Try extracting document file from bib data.
        Raises NoDocumentFile if not found.

        Parameters:
        -----------
        remove: default: False
            remove field after extracting information
        """
        try:
            field = self.bibentry.fields['file']
            # Check if this is mendeley specific
            for f in field.split(':'):
                if len(f) > 0:
                    break
            if remove:
                self.bibentry.fields.pop('file')
            # This is a hck for Mendeley. Make clean
            if f[0] != '/':
                f = '/' + f
            return f
        except (KeyError, IndexError):
            raise(NoDocumentFile('No file found in bib data.'))

    @classmethod
    def load(cls, bibpath, metapath=None):
        key, entry = cls.get_bibentry(bibpath)
        if metapath is None:
            metadata = None
        else:
            metadata = files.read_yamlfile(metapath)
        p = Paper(bibentry=entry, metadata=metadata, citekey=key)
        return p

    @classmethod
    def get_bibentry(cls, bibfile):
        """Extract first entry (supposed to be the only one) from given file.
        """
        bib_data = files.load_externalbibfile(bibfile)
        first_key = bib_data.entries.keys()[0]
        first_entry = bib_data.entries[first_key]
        return first_key, first_entry

    @classmethod
    def create_meta(cls):
        return BASE_META.copy()

    @classmethod
    def many_from_path(cls, bibpath, fatal=True):
        """Extract list of papers found in bibliographic files in path.
        """
        bibpath = files.clean_path(bibpath)
        if os.path.isdir(bibpath):
            all_files = [os.path.join(bibpath, f) for f in os.listdir(bibpath)
                    if os.path.splitext(f)[-1] in files.BIB_EXTENSIONS]
        else:
            all_files = [bibpath]
        bib_data = [files.load_externalbibfile(f) for f in all_files]
        if fatal:
            return [Paper(bibentry=b.entries[k], citekey=k)
                    for b in bib_data for k in b.entries]
        else:
            papers = []
            for b in bib_data:
                for k in b.entries:
                    try:
                        papers.append(Paper(bibentry=b.entries[k], citekey=k))
                    except ValueError, e:
                        print "Warning, skipping paper (%s)." % e
            return papers