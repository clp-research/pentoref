"""IO.py: Functions which read in the PentoRef sub-corpora in their different
formats and convert them to either Pandas dataframes or databases.
There are also functions to save these objects to files.
"""
from IOutils import create_data_from_transcriptions_and_xml_data
from IOutils import write_corpus_to_database
from os.path import abspath, join
from pandas import DataFrame


def convert_subcorpus_raw_data_to_sqlite_database(corpus_dir):
    """Converts the subcorpus to a large sqlite database with all
    the information for all interactions in the corpus.

    :param corpus_dir: str, the directory path of the subcorpus,
    e.g. PENTOREF_TAKE
    """
    corpus = corpus_dir.split("/")[-1].split("_")[0]
    dfwords, dfutts, dfrefs, dfscenes, dfactions = \
        convert_subcorpus_raw_data_to_dataframes(corpus_dir)
    write_corpus_to_database(corpus, dfwords, dfutts, dfrefs, dfscenes,
                             dfactions)


def convert_subcorpus_raw_data_to_dataframes(corpus_dir):
    """Converts the subcorpus to 4 Pandas dataframes containing info for
    words, utterances, references and scenes

    :param corpus_dir: str, the directory path of the subcorpus,
    e.g. PENTOREF_TAKE
    """
    path = abspath(corpus_dir)
    tgpath = join(path, 'derived_data/transcription_annotation')
    xmlpath = join(path, 'derived_data/multimodal_data/scene_information')
    corpus = corpus_dir.split("/")[-1].split("_")[0]

    words, utterances, references, scenes, actions =\
        create_data_from_transcriptions_and_xml_data(corpus, tgpath, xmlpath)
    dfwords = DataFrame(words)
    dfutts = DataFrame(utterances)
    dfrefs = DataFrame(references)
    dfscenes = DataFrame(scenes)
    dfactions = DataFrame(actions)
    return dfwords, dfutts, dfrefs, dfscenes, dfactions
