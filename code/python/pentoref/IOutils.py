from __future__ import division
from os import listdir
from os.path import isdir, abspath, join, splitext
from re import match, sub, findall, finditer
from lxml.etree import parse
# from pandas import DataFrame
import sqlite3 as sqlite
from copy import deepcopy
import pympi
from tgt import read_textgrid
from textblob_de.lemmatizers import PatternParserLemmatizer
from textblob_de import TextBlobDE


def get_transcription_or_annotation_input_format(annotation_dir):
    """
    :returns: textgrid|eaf|other
    """
    for name in listdir(annotation_dir):
        if isdir(join(annotation_dir, name)):
            for name2 in listdir(join(annotation_dir, name)):
                if not isdir(name2):
                    sname2 = splitext(name2)
                    if sname2[1].lower() == '.' + "eaf":
                        return "eaf"
    return "textgrid"


def textgrid_to_dict(tgfile):
    """Returns a dict with the tier names as keys and a list of
    intervals of (start_time, end_time, text) as values.

    :param tgfile: path to textgrid file"""
    try:
        textgrid = read_textgrid(tgfile, encoding='utf-8')
    except:
        textgrid = read_textgrid(tgfile, encoding='utf-16')
    tgdict = dict()
    for tiername in textgrid.get_tier_names():
        tgdict[tiername] = []
        for textinterval in textgrid.get_tier_by_name(tiername):
            if textinterval.text != '<sil>':
                tgdict[tiername].append((float(textinterval.start_time),
                                         float(textinterval.end_time),
                                         str(textinterval.text
                                             .encode("utf-8"))))
    return tgdict


def eaf_to_dict(eaf_file):
    """Returns a dict with the tier names as keys and a list of
    intervals of (start_time, end_time, text) as values.

    :param eaf_file: path to .eaf file"""
    interval_dict = dict()
    eafob = pympi.Elan.Eaf(eaf_file)
    for tier_name in eafob.get_tier_names():
        interval_dict[tier_name] = [(x[0]/1000, x[1]/1000, x[2]) for x in
                                    sorted(
                                    eafob.
                                    get_annotation_data_for_tier(tier_name),
                                    key=lambda x: x[1])
                                    ]
    return interval_dict


def group1(m):
    return m.group(1)


def clean_utt(utt, literal=False):
    if not literal:
        #replace variants, partial and misspoken words with standard spelling
        utt = sub("""<[vpm]="(.+?)">.+?</[vpm]>""", group1, utt)
        #remove fillers like "{F aehm}" entirely
        utt = sub("""{.*?}""", "", utt)
        
        #TO DO: resolve complex replacements like "(der + der) + die) Katze"
        
    else:
        #remove brackets from fillers, i.e. "{F aehm}" becomes "aehm"
        utt = sub("""{(.*?)}""",group1,utt)
    #remove all remaining xml-style tags    
    utt = sub("""<.*?>""","",utt)
    #remove open tags at the end of an utterance (can be removed once problems with the TextGrids are fixed)
    utt = sub("""<.*$""","",utt)
    #remove all remaining punctuation and brackets
    utt = sub("""[\.:;,\(\)\+\$]""","",utt)
    #remove whitespace at the beginning and end of an utterance
    utt = utt.strip()
    #replace any amount of whitespace with a single space
    utt = sub("""\s+"""," ",utt)
    return utt


def parse_refs(utt):
    refs = list()
    for m in finditer('<ref\s+((id|piece|location)=".*?"\s*)*>(.*?)</ref>',
                      utt):
        ref = dict()
        ref['text'] = m.group(3).strip()
        for attribute in ['id', 'piece', 'location']:
            m_attribute = match('.*?'+attribute+'="(.*?)".*?', m.group(0))
            if m_attribute:
                ref[attribute] = m_attribute.group(1)
            else:
                ref[attribute] = None
        refs.append(ref)
    if len(refs) > 0:
        return refs
    else:
        return None


def find_old(tgdict, query, log):
    start, end, text = query
    results = dict()
    for tiername in tgdict.keys():
        if 'comment' not in tiername.lower()\
                and 'lh' not in tiername.lower()\
                and 'rh' not in tiername.lower():
            candidates = []
            for interval in tgdict[tiername]:
                if interval[0] < end and interval[1] > start:
                    candidates.append(interval)
            if len(candidates) == 1:
                results[tiername] = candidates[0]
            elif len(candidates) > 1:
                previous_overlap = 0
                best_candidate_nr = 0
                for nr in range(len(candidates)):
                    overlap = min(end, interval[1] - max(start, interval[0]))
                    if overlap > previous_overlap:
                        best_candidate_nr = nr
                log.write(str(start) + ' seconds: ' + str(len(candidates)) +
                          ' overlapping intervals found in tier "' +
                          tiername + '" for interval "' + text +
                          '". The interval with the' +
                          ' largest overlap has been used.\n')
                results[tiername] = candidates[best_candidate_nr]
    return results


def find(tgdict, query, log):
    return find_subdict_from_textgrid_dict(tgdict, query, log)

    
def find_subdict_from_textgrid_dict(tgdict, query, log):
    start, end, text = query
    results = dict()
    for tiername in tgdict.keys():
        if 'words' not in tiername.lower() \
                and 'comment' not in tiername.lower():
            candidates = []
            for interval in tgdict[tiername]:
                if interval[0] < end and interval[1] > start:
                    candidates.append(interval)
            if len(candidates) == 1:
                results[tiername] = candidates[0]
            elif len(candidates) > 1:
                previous_overlap = 0
                best_candidate_nr = 0
                for nr in range(len(candidates)):
                    overlap = min(end, interval[1] - max(start, interval[0]))
                    if overlap > previous_overlap:
                        best_candidate_nr = nr
                log.write(str(start)+' seconds: '+str(len(candidates)) +
                          ' overlapping intervals found in tier "' +
                          tiername+'"for interval "' + text +
                          '". The interval with the' +
                          ' largest overlap has been used.\n')
                results[tiername] = candidates[best_candidate_nr]
    return results


def get_data_from_transcriptions(tgpath, trans_format='textgrid'):
    """Returns a dict of dicts (with intervals) with the names of the
    dialogue pair as the key and the dict of intervals (where their
    keys are the tier names) as values.
    """
    def file_to_dict(filepath):
        if trans_format == "textgrid":
            return textgrid_to_dict(filepath)
        if trans_format == "eaf":
            return eaf_to_dict(filepath)

    interval_dicts = dict()
    for name in listdir(tgpath):
        if isdir(join(tgpath, name)):
            for name2 in listdir(join(tgpath, name)):
                if not isdir(name2):
                    sname2 = splitext(name2)
                    if sname2[1].lower() == '.' + trans_format:
                        interval_dicts[sname2[0]] = file_to_dict(join(
                                                                    tgpath,
                                                                    name,
                                                                    name2))
    print str(len(interval_dicts.keys())) + ' TextGrids read.'
    return interval_dicts


def get_data_from_xml(xmlpath):
    tiles = dict()
    landmarks = dict()
    scene_descriptions = dict()
    for folder in listdir(xmlpath):
        print folder
        print join(xmlpath, folder)
        if not isdir(join(xmlpath, folder)):
            continue
        for f_path in listdir(join(xmlpath, folder)):
            if not isdir(f_path):
                name, ext = splitext(f_path)
                if ext.lower() == '.txt':
                    if 'final-selected' in name:
                        tiles[folder+'_'+name[3:-15]] = (open(join(xmlpath,
                                                                   folder,
                                                                   f_path))
                                                         .read())
                    elif 'landmark' in name:
                        landmarks[folder+'_'+name[3:-9]] = \
                            (open(join(xmlpath, folder, f_path)).read())
                elif ext.lower() == '.xml' and 's' not in name:
                    # print join(xmlpath, folder, f_path)
                    scene_descriptions[folder+'_'+name[3:]] = \
                            parse(open(join(xmlpath, folder, f_path)))

    print str(len(tiles.keys())+len(landmarks.keys())) + ' text files read. '\
        + str(len(scene_descriptions)) + ' XML files parsed.'
    return tiles, landmarks, scene_descriptions


def create_data_from_transcriptions_and_xml_data_new(corpus, transcr_path,
                                                 xmlpath):
    """Returns tuple:
    words, utterances, references, scenes
    """
    tiles, landmarks, scene_descriptions = get_data_from_xml(xmlpath)
    transcr_format = get_transcription_or_annotation_input_format(transcr_path)
    textgrids = get_data_from_transcriptions(transcr_path, transcr_format)
    print corpus
    words = list()
    utterances = list()
    references = list()
    scenes = list()
    actions = list()
    regex_rel = '.*?<rel>(.*?)</rel>.*?'
    regex_lm = '.*?<lm>(.*?)</lm>.*?'
    regex_duel = '{F|}|<.*?>'
    log = open(corpus+'.log', 'w')
    count = 1
    utt_id = 0
    lemmatizer = PatternParserLemmatizer()
    speakers = ['A']
    if corpus == 'PENTOCV':
        speakers = ['A', 'B']
    print('Processing:')
    
    for run in textgrids.keys():
        print(run+'...')
        log.write('\n'+run+'\nreferences/scenes\n\n')
        if corpus == 'PENTOCV':
            for key in scene_descriptions.keys():
                skey = key.split('_')
                rx = skey[0]
                time = float(skey[1])/1000
                if rx == run:
                    for piece in scene_descriptions[key].findall('object'):
                        current_piece = dict()
                        current_piece['timestampID'] = time
                        current_piece['pieceID'] = piece.get('id')
                        current_piece['isLandmark'] = piece.get('isLandmark')
                        current_piece['isTarget'] = piece.get('isTarget')
                        current_piece['position_global'] =\
                            piece[0].get('global')
                        current_piece['position_x'] = piece[0].get('x')
                        current_piece['position_y'] = piece[0].get('y')
                        current_piece['shape'] = piece[1].get('BestResponse')
                        current_piece['shape_distribution'] = ','.join(
                            [letter + ':' + piece[1][0].get(letter)
                             for letter in ['F',
                                            'I',
                                            'L',
                                            'N',
                                            'P',
                                            'T',
                                            'U',
                                            'V',
                                            'W',
                                            'X',
                                            'Y',
                                            'Z']])
                        current_piece['shape_orientation'] = \
                            piece[1][1].get('value')
                        current_piece['shape_skewness_horizontal'] = \
                            piece[1][2].get('horizontal')
                        current_piece['shape_skewness_vertical'] = \
                            piece[1][2].get('vertical')
                        current_piece['shape_edges'] = piece[1][3].get('value')
                        current_piece['colour'] = piece[2].get('BestResponse')
                        current_piece['colour_distribution'] = \
                            ','.join([colour + ':' +
                                      str(piece[2][0].get(colour))
                                      for colour in ['Blue',
                                                     'Brown',
                                                     'Grey',
                                                     'Gray',
                                                     'Green',
                                                     'Orange',
                                                     'Pink',
                                                     'Purple',
                                                     'Red',
                                                     'Yellow']])
                        current_piece['colour_hsv'] = ','.join(
                            [letter + ':' + piece[2][1].get(letter)
                             for letter in ['H', 'S', 'V']])
                        current_piece['colour_rgb'] = ','.join(
                            [letter + ':' + piece[2][2].get(letter)
                             for letter in ['B', 'G', 'R']])
                        try:
                            current_piece['gameID'] = run + '_' + find(
                                textgrids[run], (time, time, ''), log)
                            ['Part'][2]
                        except:
                            current_piece['gameID'] = None
                            log.write(str(time) + ' seconds:' +
                                      ' No gameID could be found in ' +
                                      str(run) + '.\n')
                        scenes.append(current_piece)
        else:
            for interval in textgrids[run]['Episode']:
                start, end, text = interval
                current_ref = dict()
                try:
                    current_ref['gameID'] = run + '_' + text
                    current_ref['pieceID'] = tiles[current_ref['gameID']]
                    try:
                        current_ref['landmarkID'] = \
                            landmarks[current_ref['gameID']]
                    except:
                        current_ref['landmarkID'] = None
                    current_ref['refID'] = count
                    count += 1
                    references.append(current_ref)
                except:
                    log.write(
                              str(start) +
                              ' seconds: No selected tile could be found' +
                              ' for gameID "' +
                              current_ref['gameID'] +
                              '". No reference has been included.\n'
                        )
                try:
                    if corpus == 'TAKE':
                        for piece in scene_descriptions[
                                                current_ref['gameID']].\
                                    findall('.//piece'):
                            current_piece = dict()
                            current_piece['gameID'] = current_ref['gameID']
                            current_piece['pieceID'] = piece.get('id')
                            current_piece['shape'] = piece.get('type')
                            current_piece['colour'] = piece.get('color')
                            current_piece['gridPosition'] = piece\
                                .find('start-field').text
                            current_piece['mirrored'] = piece\
                                .find('posture').get('isMirrored')
                            current_piece['orientation'] = piece\
                                .find('posture').get('rotation')
                            scenes.append(deepcopy(current_piece))
                    elif corpus == 'TAKECV':
                        for piece in scene_descriptions[
                                                current_ref['gameID']
                                                .replace('.', '_')]\
                                                .findall('timestamp/object'):
                            current_piece = dict()
                            current_piece['gameID'] = current_ref['gameID']
                            current_piece['pieceID'] = piece.get('id')
                            current_piece['isLandmark'] = piece\
                                .get('isLandmark')
                            current_piece['isTarget'] = piece.get('isTarget')
                            current_piece['position_global'] = piece[0]\
                                .get('global')
                            current_piece['position_x'] = piece[0].get('x')
                            current_piece['position_y'] = piece[0].get('y')
                            current_piece['shape'] = piece[1].get(
                                                            'BestResponse')
                            current_piece['shape_distribution'] = ','.join(
                                            [letter + ':' + piece[1][0]
                                             .get(letter) for letter in
                                             ['F', 'I', 'L', 'N', 'P', 'T',
                                              'U', 'V', 'W', 'X', 'Y', 'Z']])
                            current_piece['shape_orientation'] = piece[1][1]\
                                .get('value')
                            current_piece['shape_skewness_horizontal'] = \
                                piece[1][2].get('horizontal')
                            current_piece['shape_skewness_vertical'] = \
                                piece[1][2].get('vertical')
                            current_piece['shape_edges'] = piece[1][3]\
                                .get('value')
                            current_piece['colour'] = piece[2]\
                                .get('BestResponse')
                            current_piece['colour_distribution'] = ','\
                                .join([colour + ':' + str(piece[2][0]
                                                          .get(colour))
                                       for colour in ['Blue',
                                                      'Brown',
                                                      'Grey',
                                                      'Green',
                                                      'Orange',
                                                      'Pink',
                                                      'Purple',
                                                      'Red',
                                                      'Yellow']])
                            current_piece['colour_hsv'] = ','.join(
                                                    [letter + ':' +
                                                     piece[2][1].get(letter)
                                                     for letter in
                                                     ['H', 'S', 'V']])
                            current_piece['colour_rgb'] = \
                                ','.join([letter + ':' + piece[2][2]
                                          .get(letter)
                                          for letter in ['B', 'G', 'R']])
                            scenes.append(deepcopy(current_piece))
                except:
                    log.write(
                        str(start) + ' seconds:' +
                        'No scene information could be found for gameID "' +
                        current_ref['gameID'] +
                        '". No scene has been included.\n'
                        )
 
    log.write('\nutterances\n\n')
    utt_id = 0
#     for interval in textgrids[run]['A-utts']:
#         start, end, text = interval
#         if text != 'p':
#             utt_id += 1
#             utt_start, utt_end, _ = interval
#             try:
#                 episode_lastfind = find_subdict_from_textgrid_dict(
#                                             textgrids[run],
#                                             interval, log)
#                 ['Episode'][2]
#             except:
#                 log.write(str(start) +
#                           ' seconds:' +
#                           'No overlapping interval found in tier' +
#                           ' "episodes" for interval "' + text +
#                           '". The previous interval has been used.\n')
#             episode = episode_lastfind
#             current_utt = dict()
#             current_utt['utt'] = text
#             if corpus == 'TAKECV':
#                 m = match(regex_rel, text)
#                 if m:
#                     current_utt['rel'] = m.group(1).strip()
#                 else:
#                     current_utt['rel'] = None
#                 m = match(regex_lm, text)
#                 if m:
#                     current_utt['lm'] = m.group(1).strip()
#                 else:
#                     current_utt['lm'] = None
#             current_utt['gameID'] = run + '_' + episode
#             current_utt['uttID'] = utt_id
#             current_utt['starttime'] = utt_start
#             current_utt['endtime'] = utt_end
#             utterances.append(deepcopy(current_utt))
#             if corpus == 'TAKECV':
#                 utt_words = sub(regex_duel, '', interval[2]).strip()\
#                     .split()
#                 for i in range(len(utt_words)):
#                     current_word = dict()
#                     current_word['word'] = utt_words[i]
#                     current_word['gameID'] = current_utt['gameID']
#                     current_word['uttID'] = current_utt['uttID']
#                     current_word['position'] = i + 1
#                     words.append(current_word)
#         if corpus == 'TAKE':
#             log.write('\nwords\n\n')
#             utt_id = 0
#             previous_utt_id = 0
#             previous_utt = ''
#             for interval in textgrids[run]['A-words']:
#                 current_word = dict()
#                 start, end, text = interval
#                 current_word['word'] = text
#                 current_word['starttime'] = start
#                 current_word['endtime'] = end
#                 try:
#                     episode_lastfind = find_subdict_from_textgrid_dict(
#                                         textgrids[run], interval,
#                                         log)['Episode'][2]
#                 except:
#                     log.write(
#                         str(start) +
#                         ' seconds: No overlapping interval found in' +
#                         ' tier "episodes" for interval "' + text +
#                         '". The previous interval has been used.\n')
#                 episode = episode_lastfind
#                 current_word['gameID'] = run + '_' + episode
#                 current_word['refID'] = ''
#                 for ref in references:
#                     if ref['gameID'] == current_word['gameID']:
#                         current_word['refID'] = ref['refID']
#                 try:
#                     utt_lastfind = find_subdict_from_textgrid_dict(
#                                                         textgrids[run],
#                                                         interval,
#                                                         log)['A-utts'][2]
#                 except:
#                     log.write(str(start) +
#                               ' seconds: No overlapping interval found' +
#                               ' in tier "utterances" for interval "' +
#                               text +
#                               '". The previous interval has been used.\n')
#                 utt = utt_lastfind
#                 if utt != previous_utt:
#                     utt_id += 1
#                 current_word['uttID'] = utt_id
#                 if utt_id > previous_utt_id:
#                     position = 1
#                 else:
#                     position += 1
#                 current_word['position'] = position
#                 previous_utt = utt
#                 previous_utt_id = utt_id
#                 if current_word['refID'] != '':
#                     words.append(current_word)
#                 else:
#                     log.write(
#                         str(start) +
#                         ' seconds: No reference found for interval "' +
#                         text + '". No word has been included.\n'
#                         )

 
    for speaker in speakers:
        previous_role = None
        for interval in textgrids[run][speaker+'-utts']:
            start,end,text = interval
            if text != 'p':
                utt_id += 1
                utt_start,utt_end,utt_text = interval
                if corpus == 'PENTOCV':
                    try:
                        episode_lastfind = find(textgrids[run],interval,log)['Part'][2]
                    except:
                        log.write(str(start)+' seconds: No overlapping interval found in tier "Part" for interval "'+text+'". If possible, the previous interval will be used.\n')
                try:
                    episode = episode_lastfind
                except:
                    episode = None
                    log.write(str(start)+'No previous episode could be found.\n')
                current_utt = dict()
                current_utt['utt'] = text
                current_utt['utt_clean'] = clean_utt(text)
                if corpus == 'TAKECV':
                    m = match(regex_rel,text)
                    if m:
                        current_utt['rel'] = m.group(1).strip()
                    else:
                        current_utt['rel'] = None
                    m = match(regex_lm,text)
                    if m:
                        current_utt['lm'] = m.group(1).strip()
                    else:
                        current_utt['lm'] = None
                if corpus == 'PENTOCV':
                    try:
                        current_utt['gameID'] = run+'_'+find(textgrids[run],interval,log)['Part'][2]
                    except:
                        current_utt['gameID'] = None
                        log.write(str(time)+' seconds: No gameID could be found in '+str(run)+'.\n')
                    matches = parse_refs(text)
                    if matches:
                        for m in matches:
                            current_ref = dict()
                            current_ref['refID'] = count
                            count += 1
                            current_ref['uttID'] = utt_id
                            current_ref['gameID'] = current_utt['gameID']
                            current_ref['text'] = m['text']
                            current_ref['id'] = m['id']
                            current_ref['piece'] = m['piece']
                            current_ref['location'] = m['location']
                            references.append(current_ref)
                else:
                    current_utt['gameID'] = run + '_' + episode
                current_utt['uttID'] = utt_id
                current_utt['starttime'] = utt_start
                current_utt['endtime'] = utt_end
                if len(speakers) > 1:
                    current_utt['speaker'] = speaker
                    try:
                        current_utt['role'] = {role.split()[0]:role.split()[1] for role in find(textgrids[run],interval,log)['Roles'][2].split(', ')}[speaker]
                        previous_role = current_utt['role']
                    except:
                        current_utt['role'] = previous_role
                if corpus == 'TAKE':
                    current_utt['dialogue-act'] = find(textgrids[run],interval,log)[speaker+'-dialogue-acts'][2]
                utterances.append(current_utt)
                if corpus != 'TAKE':
                    utt_words = TextBlobDE(sub(regex_duel,'',current_utt['utt_clean'])).words
                    utt_lemmata = lemmatizer.lemmatize(current_utt['utt_clean'])
                    try:
                        for i in range(len(utt_words)):
                            current_word = dict()
                            current_word['word'] = str(utt_words[i])
                            try:
                                current_word['lemma'], current_word['tag'] = utt_lemmata[i]
                            except:
                                current_word['lemma'], current_word['tag'] = None, None
                                log.write(str(start)+' seconds: Lemmatization has failed for interval "'+text+'".\n')
                            current_word['gameID'] = current_utt['gameID']
                            current_word['uttID'] = current_utt['uttID']
                            current_word['position'] = i + 1
                            words.append(current_word)
                    except:
                        pass
 
        if corpus == 'TAKE':
            utt_id = 0
            previous_utt_id = 0
            previous_utt = ''
            position = 1
            for interval in textgrids[run][speaker+'-words']:
                if len(interval) > 0:
                    current_word = dict()
                    start,end,text = interval
                    current_word['word'] = text
                    current_word['starttime'] = start
                    current_word['endtime'] = end
                    try:
                        current_word['lemma'], current_word['tag'] = lemmatizer.lemmatize(text)[0]
                    except:
                        current_word['lemma'], current_word['tag'] = None, None
                        log.write(str(start)+' seconds: Lemmatization has failed for interval "'+text+'".\n')
                    try:
                        episode_lastfind = find(textgrids[run],interval,log)['Episode'][2]
                    except:
                        log.write(str(start)+' seconds: No overlapping interval found in tier "Episode" for interval "'+text+'". If possible, the previous interval will be used.\n')
                    try:
                        episode = episode_lastfind
                    except:
                        episode = None
                        log.write(str(start)+'No previous episode could be found.\n')
                    current_word['gameID'] = run + '_' + episode
                    current_word['refID'] = ''
                    for ref in references:
                        if ref['gameID'] == current_word['gameID']:
                            current_word['refID'] = ref['refID']
                    try:
                        utt_lastfind = find(textgrids[run],interval,log)[speaker+'-utts'][2]
                    except:
                        log.write(str(start)+' seconds: No overlapping interval found in tier "'+speaker+'-utts" for interval "'+text+'". The previous interval has been used.\n')
                    utt = utt_lastfind
                    if utt != previous_utt:
                        utt_id += 1
                    current_word['uttID'] = utt_id
                    if utt_id > previous_utt_id:
                        position = 1
                    else:
                        position += 1
                    current_word['position'] = position
                    previous_utt = utt
                    previous_utt_id = utt_id
                    if current_word['refID'] != '':
                        words.append(current_word)
                    else:
                        log.write(str(start)+' seconds: No reference found for interval "'+text+'". No word has been included.\n')

    # Get actions if PentoCV
    if corpus == 'PENTOCV':
        log.write('\nactions\n\n')
        for hand in ['lh', 'rh']:
            for interval in textgrids[run][hand]:
                start, end, text = interval
                current_action = dict()
                current_action['starttime'] = start
                current_action['endtime'] = end
                current_action['hand'] = hand
                try:
                    current_action['action'], current_action['piece'] =\
                        text.split(':')
                except:
                    current_action['action'] = text
                    current_action['piece'] = None
                    log.write(str(start) + ' seconds: The action "' + text +
                              '" could not be read correctly.\n')
                try:
                    current_action['gameID'] = run+'_'+find(
                                                        textgrids[run],
                                                        interval,log)['Part'][2]
                    actions.append(current_action)
                except:
                    log.write(str(start) +
                              ' seconds: No gameID found for interval "' +
                              text + '". No action has been included.\n')

    print('Done.')
    log.close()
    return words, utterances, references, scenes, actions


# THE OLD STUFF THAT WORKS

def get_data_from_textgrids(tgpath):
    textgrids = dict()
    for name in listdir(tgpath):
        if isdir(join(tgpath,name)):
            for name2 in listdir(join(tgpath,name)):
                if not isdir(name2):
                    sname2 = splitext(name2)
                    if sname2[1].lower() == '.textgrid':
                        textgrids[sname2[0]] = textgrid_to_dict(join(tgpath,name,name2))
    print str(len(textgrids.keys()))+' TextGrids read.'
    return textgrids

def create_data_from_transcriptions_and_xml_data(corpus,tgpath,xmlpath):
    """Returns tuple:
    words, utterances, references, scenes
    """
    #get data from the paths
    tiles, landmarks, scene_descriptions = get_data_from_xml(xmlpath)
    textgrids = get_data_from_textgrids(tgpath)
    
    print corpus
    
    words = list()
    utterances = list()
    references = list()
    scenes = list()
    regex_rel = '.*?<rel>(.*?)</rel>.*?'
    regex_lm = '.*?<lm>(.*?)</lm>.*?'
    regex_duel = '{F|}|<.*?>'
    log = open(corpus+'.log','w')
    count = 1
    print('Processing:')
    for run in textgrids.keys():
        print(run+'...')

        log.write('\n'+run+'\nreferences/scenes\n\n')    
        for interval in textgrids[run]['Episode']:
            start,end,text = interval
            current_ref = dict()
            try:
                current_ref['gameID'] = run + '_' + text
                current_ref['pieceID'] = tiles[current_ref['gameID']]
                try:
                    current_ref['landmarkID'] = landmarks[current_ref['gameID']]
                except:
                    current_ref['landmarkID'] = None
                current_ref['refID'] = count
                count += 1
                references.append(current_ref)
            except:
                log.write(str(start)+' seconds: No selected tile could be found for gameID "'+current_ref['gameID']+'". No reference has been included.\n')

            try:
                if corpus == 'TAKE':
                    for piece in scene_descriptions[current_ref['gameID']].findall('.//piece'):
                        current_piece = dict()
                        current_piece['gameID'] = current_ref['gameID']
                        current_piece['pieceID'] = piece.get('id')
                        current_piece['shape'] = piece.get('type')
                        current_piece['colour'] = piece.get('color')
                        current_piece['gridPosition'] = piece.find('start-field').text
                        current_piece['mirrored'] = piece.find('posture').get('isMirrored')
                        current_piece['orientation'] = piece.find('posture').get('rotation')
                        scenes.append(deepcopy(current_piece))
                elif corpus == 'TAKECV':
                    for piece in scene_descriptions[current_ref['gameID'].replace('.','_')].findall('timestamp/object'):
                        current_piece = dict()
                        current_piece['gameID'] = current_ref['gameID']
                        current_piece['pieceID'] = piece.get('id')
                        current_piece['isLandmark'] = piece.get('isLandmark')
                        current_piece['isTarget'] = piece.get('isTarget')
                        current_piece['position_global'] = piece[0].get('global')
                        current_piece['position_x'] = piece[0].get('x')
                        current_piece['position_y'] = piece[0].get('y')
                        current_piece['shape'] = piece[1].get('BestResponse')
                        current_piece['shape_distribution'] = ','.join([letter+':'+piece[1][0].get(letter) for letter in ['F','I','L','N','P','T','U','V','W','X','Y','Z']])
                        current_piece['shape_orientation'] = piece[1][1].get('value')
                        current_piece['shape_skewness_horizontal'] = piece[1][2].get('horizontal')
                        current_piece['shape_skewness_vertical'] = piece[1][2].get('vertical')
                        current_piece['shape_edges'] = piece[1][3].get('value')
                        current_piece['colour'] = piece[2].get('BestResponse')
                        current_piece['colour_distribution'] = ','.join([colour+':'+str(piece[2][0].get(colour)) for colour in ['Blue','Brown','Grey','Green','Orange','Pink','Purple','Red','Yellow']])
                        current_piece['colour_hsv'] = ','.join([letter+':'+piece[2][1].get(letter) for letter in ['H','S','V']])
                        current_piece['colour_rgb'] = ','.join([letter+':'+piece[2][2].get(letter) for letter in ['B','G','R']])
                        scenes.append(deepcopy(current_piece))
            except:
                log.write(str(start)+' seconds: No scene information could be found for gameID "'+current_ref['gameID']+'". No scene has been included.\n')

        log.write('\nutterances\n\n')
        utt_id = 0

        for interval in textgrids[run]['A-utts']:
            start,end,text = interval
            if text != 'p':
                utt_id += 1
                utt_start,utt_end,utt_text = interval
                try:
                    episode_lastfind = find_subdict_from_textgrid_dict(textgrids[run],interval,log)['Episode'][2]
                except:
                    log.write(str(start)+' seconds: No overlapping interval found in tier "episodes" for interval "'+text+'". The previous interval has been used.\n')
                episode = episode_lastfind
                current_utt = dict()
                current_utt['utt'] = text
                if corpus == 'TAKECV':
                    m = match(regex_rel,text)
                    if m:
                        current_utt['rel'] = m.group(1).strip()
                    else:
                        current_utt['rel'] = None
                    m = match(regex_lm,text)
                    if m:
                        current_utt['lm'] = m.group(1).strip()
                    else:
                        current_utt['lm'] = None
                current_utt['gameID'] = run + '_' + episode
                current_utt['uttID'] = utt_id
                current_utt['starttime'] = utt_start
                current_utt['endtime'] = utt_end
                utterances.append(deepcopy(current_utt))
                if corpus == 'TAKECV':
                    utt_words = sub(regex_duel,'',interval[2]).strip().split()
                    for i in range(len(utt_words)):
                        current_word = dict()
                        current_word['word'] = utt_words[i]
                        current_word['gameID'] = current_utt['gameID']
                        current_word['uttID'] = current_utt['uttID']
                        current_word['position'] = i + 1
                        words.append(current_word)

        if corpus == 'TAKE':
            log.write('\nwords\n\n')
            utt_id = 0
            previous_utt_id = 0
            previous_utt = ''
            for interval in textgrids[run]['A-words']:
                current_word = dict()
                start,end,text = interval
                current_word['word'] = text
                current_word['starttime'] = start
                current_word['endtime'] = end
                try:
                    episode_lastfind = find_subdict_from_textgrid_dict(textgrids[run],interval,log)['Episode'][2]
                except:
                    log.write(str(start)+' seconds: No overlapping interval found in tier "episodes" for interval "'+text+'". The previous interval has been used.\n')
                episode = episode_lastfind
                current_word['gameID'] = run + '_' + episode
                current_word['refID'] = ''
                for ref in references:
                    if ref['gameID'] == current_word['gameID']:
                        current_word['refID'] = ref['refID']
                try:
                    utt_lastfind = find_subdict_from_textgrid_dict(textgrids[run],interval,log)['A-utts'][2]
                except:
                    log.write(str(start)+' seconds: No overlapping interval found in tier "utterances" for interval "'+text+'". The previous interval has been used.\n')
                utt = utt_lastfind
                if utt != previous_utt:
                    utt_id += 1
                current_word['uttID'] = utt_id
                if utt_id > previous_utt_id:
                    position = 1
                else:
                    position += 1
                current_word['position'] = position
                previous_utt = utt
                previous_utt_id = utt_id
                if current_word['refID'] != '':
                    words.append(current_word)
                else:
                    log.write(str(start)+' seconds: No reference found for interval "'+text+'". No word has been included.\n')

    print('Done.')
    log.close()
    return words, utterances, references, scenes, None



def write_corpus_to_database(corpus, words, utterances, references, scenes,
                             actions=None):
    db = sqlite.connect(corpus+'.db')

    if corpus == 'TAKE':

        db.execute('create table words(gameID, uttID, position,' +
                   ' starttime, endtime, word, refID)')
        for interval in words:
            db.execute('insert into words values (?,?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'position',
                                                  'starttime',
                                                  'endtime',
                                                  'word',
                                                  'refID']])

        db.execute('create table utts(gameID, uttID, starttime, endtime,' +
                   'utt, "dialogue-act")')
        for interval in utterances:
            db.execute('insert into utts values (?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'starttime',
                                                  'endtime',
                                                  'utt',
                                                  'dialogue-act']])

        db.execute('create table scenes(gameID, pieceID, shape,' +
                   ' colour, orientation, isMirrored, gridPosition)')
        for interval in scenes:
            db.execute('insert into scenes values (?,?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'pieceID',
                                                  'shape',
                                                  'colour',
                                                  'orientation',
                                                  'isMirrored',
                                                  'gridPosition']])

        db.execute('create table refs(gameID, pieceID, refID)')
        for interval in references:
            db.execute('insert into refs values (?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'pieceID',
                                                  'refID']])

    elif corpus == 'TAKECV':

        db.execute('create table words(gameID, uttID, position, word)')
        for interval in words:
            db.execute('insert into words values (?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'position',
                                                  'word']])

        db.execute('create table utts(gameID, uttID, starttime,' +
                   ' endtime, utt, rel, lm)')
        for interval in utterances:
            db.execute('insert into utts values (?,?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'starttime',
                                                  'endtime',
                                                  'utt',
                                                  'rel',
                                                  'lm']])

        db.execute('create table scenes(gameID, pieceID, isLandmark,' +
                   ' isTarget, position_global, position_x, position_y,' +
                   ' shape, shape_distribution, shape_orientation,' +
                   ' shape_skewness_horizontal, shape_skewness_vertical,' +
                   ' shape_edges, colour, colour_distribution, colour_hsv,' +
                   ' colour_rgb)')
        for interval in scenes:
            db.execute(
               'insert into scenes values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               [interval[col] for col in ['gameID',
                                          'pieceID',
                                          'isLandmark',
                                          'isTarget',
                                          'position_global',
                                          'position_x',
                                          'position_y',
                                          'shape',
                                          'shape_distribution',
                                          'shape_orientation',
                                          'shape_skewness_horizontal',
                                          'shape_skewness_vertical',
                                          'shape_edges',
                                          'colour',
                                          'colour_distribution',
                                          'colour_hsv',
                                          'colour_rgb']])
        db.execute('create table refs(gameID, pieceID, landmarkID, refID)')
        for interval in references:
            db.execute('insert into refs values (?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'pieceID',
                                                  'landmarkID',
                                                  'refID']])
    elif corpus == 'PENTOCV':
        db.execute(
                'create table words(gameID, uttID, position, word, lemma, tag)'
                )
        for interval in words:
            db.execute('insert into words values (?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'position',
                                                  'word',
                                                  'lemma',
                                                  'tag']]
                       )
        db.execute('create table utts(gameID, uttID, starttime, endtime, ' +
                   'utt, utt_clean, role, speaker)')
        for interval in utterances:
            db.execute('insert into utts values (?,?,?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'uttID',
                                                  'starttime',
                                                  'endtime',
                                                  'utt',
                                                  'utt_clean',
                                                  'role',
                                                  'speaker']])
        db.execute('create table scenes(timestampID, gameID, pieceID, ' +
                   'position_global, position_x, position_y, shape, ' +
                   'shape_distribution, shape_orientation, ' +
                   'shape_skewness_horizontal, shape_skewness_vertical, ' +
                   'shape_edges, colour, colour_distribution, ' +
                   'colour_hsv, colour_rgb)')
        for interval in scenes:
            db.execute(
                'insert into scenes values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                [interval[col] for col in ['timestampID',
                                           'gameID',
                                           'pieceID',
                                           'position_global',
                                           'position_x',
                                           'position_y',
                                           'shape',
                                           'shape_distribution',
                                           'shape_orientation',
                                           'shape_skewness_horizontal',
                                           'shape_skewness_vertical',
                                           'shape_edges',
                                           'colour',
                                           'colour_distribution',
                                           'colour_hsv',
                                           'colour_rgb']])
        db.execute('create table refs(refID, gameID, uttID, text, id, ' +
                   'piece, location)')
        for interval in references:
            db.execute('insert into refs values (?,?,?,?,?,?,?)',
                       [interval[col] for col in ['refID',
                                                  'gameID',
                                                  'uttID',
                                                  'text',
                                                  'id',
                                                  'piece',
                                                  'location']])
        db.execute('create table actions(gameID, starttime, endtime, ' +
                   'hand, action, piece)')
        for interval in actions:
            db.execute('insert into actions values (?,?,?,?,?,?)',
                       [interval[col] for col in ['gameID',
                                                  'starttime',
                                                  'endtime',
                                                  'hand',
                                                  'action',
                                                  'piece']])

    db.commit()
    db.close()


if __name__ == '__main__':
    # set this by hand
    folder = '../../sciebo/PENTOREF/TAKE_PENTOREF'
    path = abspath(folder)
    tgpath = join(path, 'transcription_annotation')
    xmlpath = join(path, 'multimodal_data/scene_information')
    corpus = folder[folder.rfind("/")+1:-9].split("_")[0]
    print corpus
    # words, utterances, references, scenes = \
    #    create_data_from_textgrids_and_xml_data(corpus,tgpath,xmlpath)
    # turn into data frames
    # dfwords = DataFrame(words)
    # dfutts = DataFrame(utterances)
    # dfrefs = DataFrame(references)
    # dfscenes = DataFrame(scenes)
    # dfscenes
