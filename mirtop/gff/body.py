"""GFF reader and creator helpers"""

from collections import defaultdict, OrderedDict
from mirtop.mirna.realign import get_mature_sequence, align_from_variants, \
    read_id, variant_to_5p, variant_to_3p, variant_to_add
from mirtop.gff.header import read_samples

import mirtop.libs.logger as mylog
logger = mylog.getLogger(__name__)


def read(fn, args):
    """Read GTF/GFF file and load into annotate, chrom counts, sample, line"""
    samples = read_samples(fn)
    lines = defaultdict(dict)
    with open(fn) as inh:
        for line in inh:
            if line.startswith("#"):
                continue
            cols = read_gff_line(line)
            if cols['start'] not in lines[cols['chrom']]:
                lines[cols['chrom']][cols['start']] = []
            uid = "%s-%s-%s" % (cols['attrb']['UID'],
                                cols['attrb']['Variant'],
                                cols['attrb']['Name'])
            lines[cols['chrom']][cols['start']].append(
                [uid,
                 cols['chrom'],
                 cols['attrb']['Expression'].strip().split(","),
                 samples,
                 line.strip()])
    return lines


def create(reads, database, sample, args):
    """Read https://github.com/miRTop/mirtop/issues/9"""
    sep = " " if args.out_format == "gtf" else "="
    seen = set()
    lines = defaultdict(defaultdict)
    seen_ann = {}
    filter_precursor = 0
    filter_score = 0
    n_hits = 0
    n_reads = 0
    n_seen = 0
    if args.add_extra:
        precursors = args.precursors
        matures = args.matures
    for r, read in reads.iteritems():
        hits = set()
        [hits.add(mature.mirna) for mature in read.precursors.values()
            if mature.mirna]
        hits = len(hits)
        if len(read.precursors) > 0:
            n_reads += 1
        for p, iso in read.precursors.iteritems():
            if not iso.mirna:
                filter_precursor += 1
                continue
            if (r, iso.mirna) not in seen:
                seen.add((r, iso.mirna))
                chrom = p
                seq = reads[r].sequence
                if iso.get_score(len(seq)) < 1:
                    filter_score += 1
                    continue
                if iso.subs:
                    iso.subs = [] if "N" in iso.subs[0] else iso.subs
                idseq = reads[r].idseq
                annotation = "%s.%s" % (chrom, idseq)
                source = "ref_miRNA" if not iso.is_iso() else "isomiR"
                strand = iso.strand
                start, end = iso.start, iso.end
                score = iso.map_score
                mirName = iso.mirna
                preName = p
                Variant = iso.formatGFF()
                Cigar = iso.cigar
                counts = read.counts
                Filter = iso.filter

                attrb = ("Read {r}; UID {idseq}; Name {mirName};"
                         " Parent {preName};"
                         " Variant {Variant}; Cigar {Cigar};"
                         " Expression {counts};"
                         " Filter {Filter}; Hits {hits};").format(**locals())
                line = ("{chrom}\t{database}\t{source}\t{start}\t{end}"
                        "\t{score}\t{strand}\t.\t{attrb}").format(**locals())
                logger.debug("GFF::%s" % line)
                if args.add_extra:
                    extra = variant_with_nt(line, precursors, matures)
                    line = "%s Changes %s;" % (line, extra)

                line = paste_columns(read_gff_line(line), sep=sep)
                if annotation in seen_ann and seq.find("N") < 0 and (
                        seen_ann[annotation].split("\t")[0].find("N") < 0):
                    logger.warning(
                        "Same isomir %s from different sequence:"
                        " \n%s and \n%s" % (annotation, line,
                                            seen_ann[annotation]))
                seen_ann[annotation] = line
                logger.debug("GFF::external %s" % iso.external)
                if start not in lines[chrom]:
                    lines[chrom][start] = []
                lines[chrom][start].append([annotation, chrom,
                                            counts, sample, line])
                logger.debug("GFF::%s" % line)
                n_hits += 1
            else:
                n_seen += 1

    logger.info("GFF miRNAs: %s" % len(lines))
    logger.info("GFF hits %s by %s reads" % (n_hits, n_reads))
    logger.info("Filtered by being duplicated: %s" % n_seen)
    logger.info("Filtered by being outside miRNA positions:"
                " %s" % filter_precursor)
    logger.info("Filtered by being low score: %s" % filter_score)
    return lines


def guess_format(line):
    return "=" if line.find("Name=") > -1 else " "


def paste_columns(cols, sep=" "):
    """
    Create GFF/GTF line from read_gff_line
    """
    cols['attrb'] = "; ".join(
        "%s%s%s" % (a, sep, cols['attrb'][a]) for a in cols['attrb'])
    return "\t".join([cols['chrom'], cols['source'], cols['type'],
                      cols['start'], cols['end'], cols['score'],
                      cols['strand'], cols['ext'], cols['attrb']])


def read_attributes(gff_line, sep=" "):
    gff_line = gff_line.strip().split("\t")[8]
    gff_dict = OrderedDict()
    for gff_item in gff_line.strip().split(";"):
        item_pair = gff_item.strip().split(sep)
        if len(item_pair) > 1:
            gff_dict[item_pair[0].strip()] = item_pair[1].strip()
    return gff_dict


def read_variant(attrb, sep=" "):
    """
    Read string in variants attribute.

    Args:
        *attrb(str)*: string in Variant attribute.

    Returns:
        *(gff_dict)*: dictionary with:
            >>> {'iso_3p': -3, ...}
    """
    gff_dict = OrderedDict()
    logger.debug("variant: %s" % attrb)
    for gff_item in attrb.strip().split(","):
        item_pair = gff_item.strip().split(":")
        if len(item_pair) > 1:
            gff_dict[item_pair[0].strip()] = int(item_pair[1].strip())
        else:
            gff_dict[item_pair[0].strip()] = True
    logger.debug("Keys found: %s" % gff_dict.keys())
    logger.debug("Values found: %s" % gff_dict.values())
    return gff_dict


def read_gff_line(line):
    """
    Read GFF/GTF line and return dictionary with fields
    """
    if line.startswith("#"):
        return line
    cols = line.strip().split("\t")
    sep = guess_format(line)
    if len(cols) != 9:
        raise ValueError("Line has less than 9 elements: %s" % line)
    fields = {'chrom': cols[0],
              'source': cols[1],
              'type': cols[2],
              'start': cols[3],
              'end': cols[4],
              'score': cols[5],
              'strand': cols[6],
              'ext': cols[7],
              'attrb': read_attributes(line, sep)}
    return fields


def variant_with_nt(line, precursors, matures):
    """
    Return nucleotides changes for each variant type
    using Variant attribute, precursor sequences and
    mature position.
    """
    cols = read_gff_line(line)
    attr = cols["attrb"]
    read = read_id(attr["UID"])
    logger.debug("GFF::BODY::precursors %s" % precursors[attr["Parent"]])
    logger.debug("GFF:BODY::mature %s" % matures[attr["Parent"]][attr["Name"]])
    t5 = variant_to_5p(precursors[attr["Parent"]],
                       matures[attr["Parent"]][attr["Name"]],
                       attr["Variant"])
    t3 = variant_to_3p(precursors[attr["Parent"]],
                       matures[attr["Parent"]][attr["Name"]],
                       attr["Variant"])
    add = variant_to_add(read,
                         attr["Variant"])
    mature_sequence = get_mature_sequence(
        precursors[attr["Parent"]],
        matures[attr["Parent"]][attr["Name"]])
    logger.debug("GFF::BODY::mature_sequence %s" % mature_sequence)
    mm = align_from_variants(read,
                             mature_sequence,
                             attr["Variant"])
    if mm == "Invalid":
        return mm
    if len(mm) > 0:
        mm = "".join(["".join(map(str, m)) for m in mm])
    else:
        mm = "0"
    return "iso_5p:%s,iso_3p:%s,iso_add:%s,iso_snp:%s" % (t5, t3, add, mm)
