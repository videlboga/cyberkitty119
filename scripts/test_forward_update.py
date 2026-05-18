from max_bot.adapter import build_update_and_context

forward_update = {'message': {'recipient': {'chat_id': 233211983, 'chat_type': 'dialog', 'user_id': 230010934}, 'timestamp': 1775063240510, 'body': {'mid': 'mid.000000000de6884f019d4a038f3e6f36', 'seq': 116330544530091830, 'text': ''}, 'sender': {'user_id': 5453945, 'first_name': 'Андрей', 'last_name': '', 'is_bot': False, 'last_activity_time': 1775063233000, 'name': 'Андрей'}, 'link': {'type': 'forward', 'message': {'mid': 'mid.000000000de6884f019d49b55fb35bee', 'seq': 116330208724999150, 'text': '', 'attachments': [{'payload': {'url': 'http://vd351.okcdn.ru/?expires=1775149640540&srcIp=10.219.7.183&pr=96&srcAg=UNKNOWN&ms=45.136.22.74&type=2&sig=u-s3GGsRNxk&ct=2&urls=185.180.203.12&clientType=11&appId=1248243456&id=13629827910239&scl=2', 'token': 'f9LHodD0cOIEPAWBuGYruv_QWI9XLV29eWxTebcGiKqr6ge5F3O6xR4u-MDSyMOSXwtouSBRocq083hjbq9o', 'id': 13189965832287}, 'type': 'audio'}]}}}}

fake_update, ctx = build_update_and_context(forward_update)
msg = fake_update.message
print('text=', getattr(msg, 'text', None))
for attr in ('document','video','audio','voice','video_note'):
    v = getattr(msg, attr, None)
    if v:
        print('found on', attr, 'file_id=', getattr(v,'file_id',None), 'file_url=', getattr(v,'file_url',None), 'mime=', getattr(v,'mime_type',None))
        break
else:
    print('no file attached')
print('ctx._sent_messages=', getattr(ctx,'_sent_messages',None))
