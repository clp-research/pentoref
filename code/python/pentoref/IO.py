"""IO.py: Functions which read in the PentoRef sub-corpora in their different
formats and convert them to either Pandas dataframes or databases.
There are also functions to save these objects to files.
"""
from IOutils import create_data_from_textgrids_and_xml_data
from os.path import abspath, join
from pandas import DataFrame


def get_transcription_or_annotation_input_format(annotation_dir):
    """
    :return textgrid|eaf|other
    """
    raise NotImplementedError


def convert_subcorpus_raw_data_to_sqlite_database(corpus_dir):
    """Converts the subcorpus to a large sqlite database with all
    the information for each utterance in the corpus.

    :param corpus_dir : str, the directory path of the subcorpus,
    e.g. PENTOREF_TAKE
    """
    raise NotImplementedError


def convert_subcorpus_raw_data_to_utterance_dataframe(corpus_dir):
    """Converts the subcorpus to a large Pandas dataframe with all
    the information for each utterance in the corpus.

    :param corpus_dir : str, the directory path of the subcorpus,
    e.g. PENTOREF_TAKE
    """
    path = abspath(corpus_dir)
    tgpath = join(path, 'derived_data/transcription_annotation')
    xmlpath = join(path, 'derived_data/multimodal_data/scene_information')
    corpus = corpus_dir.split("/")[-1].replace('_', '')

    words, utterances, references, scenes =\
        create_data_from_textgrids_and_xml_data(corpus, tgpath, xmlpath)
    dfwords = DataFrame(words)
    dfutts = DataFrame(utterances)
    dfrefs = DataFrame(references)
    dfscenes = DataFrame(scenes)
    return dfwords, dfutts, dfrefs, dfscenes
