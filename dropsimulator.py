# Diablo 2 Drop Simulation Tool
# TODO: Differentiate between classic and LoD

import csv
import random
import re

items = {} # map of id -> (dict keys:) id, name, ilvl, type, normalid, exceptionalid, eliteid
monsters = [] # (dict keys:) id, name, tc1-4[e|(N)|(H)], level
TCs = {} # map of id -> (dict keys:) id, group, level, picks, unique, set, rare, magic, nodrop, items ([(item1, weight1), (item2, weight2), ...])
itemRatios = {} # map of (version, exceptionalOrElite, classSpecific) -> (dict keys:) X, X_divisor, Y_min WHERE Y = [unique, set, rare, magic] AND X = Y + [hiquality, normal]
uniqueItems = {}
setItems = {}

def main():
    modDir = 'D:\\Programs\\Diablo II_modded\\Data\\global\\excel\\'
    vanillaTxtDir = 'D:\\Diablo2Modding\\vanilla_excel\\'
    loadAll(modDir, vanillaTxtDir)

    mon = selectDropSource()
    difficulty = 'H'
    tmp = input('Difficulty (one of: N(ormal), NM(are), H(ell)) [default=H]: ').upper()
    if tmp in ['N', 'NM', 'H']:
        difficulty = tmp
    dropType = 'u'
    tmp = input('Monster type (one of n(ormal), c(hampion), u(nique), q(uest unique)) [default=u]: ').lower()
    if tmp in ['n', 'u', 'c', 'q']:
        dropType = tmp
    mf = 0
    try:
        mf = int(input('Magic Find % (default = 0): '))
    except ValueError:
        pass
    players = 1
    try:
        players = int(input('Number of Players in game (default=1): '))
    except ValueError:
        pass
    nearbyPlayers = 0
    try:
        nearbyPlayers = int(input('Number of Players in your party, nearby (default=0): '))
    except ValueError:
        pass

    for i in range(0, 5):
        dropFromSource(mon, dropType, difficulty, mf, players, nearbyPlayers)

def dropFromSource(monster, dropType, difficulty, mf, players, nearbyPlayers):
    print('Drops from %s (id: %s):' % (monster['name'], monster['id']))
    print('-----------------------------------')
    diff = {'N':'','NM':'(N)','H':'(H)'}[difficulty]
    tc = 'tc' + str({'n':1,'c':2,'u':3,'q':4}[dropType]) + diff
    mlvl = monster['level' + diff]
    dropTC(monster[tc], mlvl, mf, players, nearbyPlayers)

def dropTC(itemOrTC, mlvl, mf, players, nearbyPlayers, maxItemDrops=6, chanceModTC=None, parentTC=None):
    # TODO: Do TCs actually get upgraded in NM/H? The TCs already seem to align with drops. E.g. if it got upgraded
    #       then Diablo would be able to drop e.g. ilvl 86 weapon, which only Baal can (from act bosses). Unless only
    #       the first step can be upgraded.
    #       Maybe only for non-bosses? Similar to how bosses also do not get their level scaled by area level.

    # Recursion exit
    if maxItemDrops <= 0:
        return 0

    # Drop direct item
    if itemOrTC not in TCs:
        dropItem(itemOrTC, mlvl, parentTC, mf, players, nearbyPlayers, chanceModTC)
        return maxItemDrops - 1

    # Drop TreasureClass
    tc = TCs[itemOrTC]

    # Update chance modifiers
    if tc['unique'] > 0:
        if chanceModTC != None:
            print('Warning: chanceModTC was overwritten. From %s to %s.' % (chanceModTC['id'], tc['id']))
        chanceModTC = tc
    
    # Do drops for negative picks
    picks = tc['picks']
    if picks < 0:
        idx = 0
        count = 0
        while picks < 0 and maxItemDrops > 0:
            picks += 1
            (item, weight) = tc['items'][idx]
            if count >= weight:
                idx += 1
                count = 0
                continue
            maxItemDrops = dropTC(item, mlvl, mf, players, nearbyPlayers, maxItemDrops, chanceModTC, tc)
            count += 1
        return maxItemDrops

    # Do drops for positive picks
    while picks > 0 and maxItemDrops > 0:
        picks -= 1
        # Calculate nodrop
        sumOfWeights = sum([w for (_, w) in tc['items']])
        nodrop = tc['nodrop']
        if nodrop > 0:
            n = int(1 + 0.5 * (players - 1) + 0.5 * nearbyPlayers)
            nodrop = int(sumOfWeights / (((sumOfWeights + nodrop) / nodrop)**n - 1) + 0.001)
        sumOfWeights += nodrop
        # Do weighted item drops
        rng = random.randrange(0, sumOfWeights) # [0, sumOfWeights)
        if rng < nodrop:
            maxItemDrops -= 1
            continue
        offset = nodrop
        for (item, weight) in tc['items']:
            if rng < (offset + weight):
                drop = item
                break
            offset += weight
        maxItemDrops = dropTC(drop, mlvl, mf, players, nearbyPlayers, maxItemDrops, chanceModTC, tc)

    return maxItemDrops

def dropItem(itemStr, mlvl, TC, mf, players, nearbyPlayers, chanceModTC):
    item = items[itemStr.split(',')[0]]
    (rarity, item) = rollRarity(item, mlvl, TC, mf, chanceModTC)
    print('dropping', item['name'], '(rarity: %s, base ilvl: %d, ilvl: %d)' % (rarity, item['ilvl'], mlvl), '[chanceModTC: %s]' % chanceModTC['id'])

def rollRarity(item, mlvl, TC, mf, chanceModTC):
    if not (TC['id'].startswith('weap') or TC['id'].startswith('armo')):
        return 'normal'
    if testRarity('unique', mlvl, item, mf, chanceModTC):
        item = upgradeToRarity(item, 'unique')
        if item != None:
            return ('unique', item)
    if testRarity('set', mlvl, item, mf, chanceModTC):
        item = upgradeToRarity(item, 'set')
        if item != None:
            return ('set', item)
    if testRarity('rare', mlvl, item, mf, chanceModTC):
        return ('rare', item)
    if testRarity('magic', mlvl, item, mf, chanceModTC):
        return ('magic', item)
    if testRarity('normal', mlvl, item, mf, chanceModTC):
        return ('normal', item)
    return 'low'

def testRarity(rarity, mlvl, item, mf, chanceModTC):
    upped = item['id'] in [item['exceptionalid'], item['eliteid']]
    classSpecific = isClassSpecificType(item['type'])
    ratios = itemRatios[(True, upped, classSpecific)]
    quality = ratios[rarity]
    quality_divisor = ratios[rarity + '_divisor']
    quality_min = (ratios[rarity + '_min'] if (rarity + '_min') in ratios else 0)
    chanceMod = chanceModTC[rarity] if rarity in chanceModTC else 0

    emf = mf
    if rarity in ['unique', 'set', 'rare']:
        mfFactor = {'unique': 250, 'set': 500, 'rare': 600}[rarity]
        emf = (mf * mfFactor)/(mf + mfFactor)
    
    ilvl = mlvl
    base_ilvl = item['ilvl']
    v = int(128 * (quality - (ilvl - base_ilvl) / quality_divisor) + 0.00001)
    v = int(v * 100 / (100 + emf) + 0.00001)
    v = max(quality_min, v) # TODO: Not sure if the game actually does this check
    v = int(v - v * chanceMod / 1024 + 0.00001)

    # if rarity == 'unique':
        # print('rolling unique for %s: v is %d' % (item['name'], v))
    return random.randrange(0, v) < 128

def upgradeToRarity(item, rarity):
    if rarity not in ['unique', 'set']
        return item
    

def isClassSpecificType(itemType):
    classSpecifics = [
        'phlm', # barb helmet
        'pelt', # druid helmet
        'head', # necro shield
        'ashd', # pala shield
        'abow', # amazon bow
        'aspe', # amazon spear
        'ajav', # amazon javeline
        'h2h', 'h2h2', # assassin claws
        'orb' # sorc orb
    ]
    return itemType in classSpecifics

def selectDropSource():
    mon = None
    while mon == None:
        typed = input('Monster: ').lower()
        if len(typed) < 3:
            print('Error: too short.')
        options = []
        for monster in monsters:
            if monster['name'].lower().startswith(typed):
                options.append(monster)
        if len(options) == 0:
            print('Error: no match.')
        elif len(options) == 1:
            monId = monster['id']
        else:
            while mon == None:
                print('Multiple matches. Choose one:')
                for i in range(len(options)):
                    print('%d. %s (id: %s)' % (i + 1, options[i]['name'], options[i]['id']))
                try:
                    idx = int(input('Choice: '))
                    mon = options[idx - 1]
                except (ValueError, IndexError):
                    print('Error: invalid choice.')
    return mon

def openTxt(modDir, vanillaDir, txt):
    try:
        f = open(modDir + txt, 'r')
        return f
    except OSError:
        f = open(vanillaDir + txt, 'r')
        return f

def readCSV(f):
    reader = csv.DictReader(f, delimiter='\t')
    return [row for row in reader]

def loadAll(modDir, vanillaDir):
    # Load Items
    with openTxt(modDir, vanillaDir, 'Misc.txt') as f:
        loadItems(f)
    with openTxt(modDir, vanillaDir, 'Weapons.txt') as f:
        loadItems(f)
    with openTxt(modDir, vanillaDir, 'Armor.txt') as f:
        loadItems(f)
    # Load Monsters
    with openTxt(modDir, vanillaDir, 'MonStats.txt') as f:
        loadMonsters(f)
    with openTxt(modDir, vanillaDir, 'SuperUniques.txt') as f:
        loadSuperUniques(f)
    # Load TC & Item Ratio
    with openTxt(modDir, vanillaDir, 'TreasureClassEx.txt') as f: 
        loadTCs(f)
    with openTxt(modDir, vanillaDir, 'ItemRatio.txt') as f: 
        loadItemRatios(f)
    # Generate TCs
    with openTxt(modDir, vanillaDir, 'Weapons.txt') as f:
        generateTCs(f, 'weap')
    with openTxt(modDir, vanillaDir, 'Armor.txt') as f:
        generateTCs(f, 'armo')

def loadItems(f):
    global items
    for row in readCSV(f):
        if 'normcode' in row:
            items[row['code']] = {'id': row['code'], 'name': row['name'], 'ilvl': intN(row['level']), 'type': row['type'],
                'normalid': row['normcode'], 'exceptionalid': row['ubercode'], 'eliteid': row['ultracode']}
        else:
            items[row['code']] = {'id': row['code'], 'name': row['name'], 'ilvl': intN(row['level']), 'type': row['type']}

def loadMonsters(f):
    global monsters
    for row in readCSV(f):
        monsters.append({'id': row['Id'], 'name': row['NameStr'],
            'tc1': row['TreasureClass1'], 'tc2': row['TreasureClass2'],
            'tc3': row['TreasureClass3'], 'tc4': row['TreasureClass4'],
            'tc1(N)': row['TreasureClass1(N)'], 'tc2(N)': row['TreasureClass2(N)'],
            'tc3(N)': row['TreasureClass3(N)'], 'tc4(N)': row['TreasureClass4(N)'],
            'tc1(H)': row['TreasureClass1(H)'], 'tc2(H)': row['TreasureClass2(H)'],
            'tc3(H)': row['TreasureClass3(H)'], 'tc4(H)': row['TreasureClass4(H)'],
            'level': intN(row['Level']), 'level(N)': intN(row['Level(N)']), 'level(H)': intN(row['Level(H)'])})

def loadSuperUniques(f):
    global monsters
    for row in readCSV(f):
        monsters.append({'id': row['Superunique'], 'name': row['Name'],
            'tc1': row['TC'], 'tc1(N)': row['TC(N)'], 'tc1(H)': row['TC(H)']})

def loadTCs(f):
    global treasureClasses
    for row in readCSV(f):
        # gather dropped items into a list
        dropItems = []
        for i in range(1, 11):
            item = row['Item' + str(i)]
            if len(item) > 0:
                weight = int(row['Prob' + str(i)])
                dropItems.append((item, weight))
        # map treasure class row
        TCs[row['Treasure Class']] = {'id': row['Treasure Class'],
            'group': intN(row['group']), 'level': intN(row['level']), 'picks': intN(row['Picks']),
            'unique': intN(row['Unique']), 'set': intN(row['Set']), 'rare': intN(row['Rare']),
            'magic': intN(row['Magic']), 'nodrop': intN(row['NoDrop']), 'items': dropItems
        }

def loadItemRatios(f):
    global itemRatios
    for row in readCSV(f):
        itemRatios[(bool(int(row['Version'])), bool(int(row['Uber'])), bool(int(row['Class Specific'])))] = {
            'unique': intN(row['Unique']), 'unique_divisor': intN(row['UniqueDivisor']), 'unique_min': intN(row['UniqueMin']),
            'rare': intN(row['Rare']), 'rare_divisor': intN(row['RareDivisor']), 'rare_min': intN(row['RareMin']),
            'set': intN(row['Set']), 'set_divisor': intN(row['SetDivisor']), 'set_min': intN(row['SetMin']),
            'magic': intN(row['Magic']), 'magic_divisor': intN(row['MagicDivisor']), 'magic_min': intN(row['MagicMin']),
            'hiquality': intN(row['HiQuality']), 'hiquality_divisor': intN(row['HiQualityDivisor']),
            'normal': intN(row['Normal']), 'normal_divisor': intN(row['NormalDivisor'])
        }

def intN(s):
    if len(s) > 0:
        return int(s)
    return 0

def generateTCs(f, prefix):
    global TCs
    for row in readCSV(f):
        # Skip 'Expansion' weapon
        if len(row['code']) == 0:
            continue
        # Skip items that cannot drop naturally
        if len(row['rarity']) == 0:
            continue
        # Align TC level to multiple of 3
        tcLvl = int(row['level'])
        while tcLvl % 3 != 0:
            tcLvl += 1
        # Create TC if it doesn't exist yet
        tcName = prefix + str(tcLvl)
        if tcName not in TCs:
            # print('Created TreasureClass: %s' % tcName)
            TCs[tcName] = {'id':tcName, 'group':0, 'level':0, 'picks':1, 'unique':0, 'set':0, 'rare':0, 'magic':0, 'nodrop':0, 'items':[]}
        # Append this item to TC
        TCs[tcName]['items'].append((row['code'], int(row['rarity'])))

if __name__ == '__main__':
    main()
