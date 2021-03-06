"""Helpers to define the header fo the GFF file"""

from mirtop.gff import gff_versions as version
import mirtop.libs.logger as mylog
logger = mylog.getLogger(__name__)


def create(samples, database, custom, filter=None):
    """Create header for GFF file.

    Args:
        *samples (list)*: character list with names for samples

        *database (str)*: name of the database.

        *custom (str)*: extra lines.

        *filter (list)*: character list with filter definition.

    Returns:
        *header (str)*: header string.
    """
    header = ""
    header += _get_gff_version()
    header += _get_database(database)
    header += _get_samples(samples)
    header += custom
    return header


def _get_gff_version():
    return ("## mirGFF3. VERSION"
            " %s\n" % version.current)


def _get_samples(samples):
    return "## COLDATA: %s" % ",".join(samples)


def _get_database(database):
    if database.lower().find("mirbase") > -1:
        so = "doi:10.25504/fairsharing.hmgte8"
    elif database.lower().find("mirgenedb") > -1:
        so = "http://mirgenedb.org"
    return ("## source-ontology: %s %s\n" % (database, so))


def _filter(filters):
    if not filters:
        return "## FILTER: PASS\n"
    return "## FILTER: %s" % ";\n".join(filters)


def read_samples(fn):
    """Read samples from the header of a GFF file.

    Args:
        *fn(str)*: GFF file to read.

    Returns:
        *(list)*: character list with sample names.
    """
    with open(fn) as inh:
        for line in inh:
            if line.startswith("## COLDATA"):
                return line.strip().split(": ")[1].strip().split(",")
    raise ValueError("%s doesn't contain COLDATA header." % fn)
