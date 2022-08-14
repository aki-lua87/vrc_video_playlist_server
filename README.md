# vrc_video_playlist_server

## About  

VRChat上で同一のURLから異なるYoutubeの動画を再生するシステム。  
iwasyncやKineL式などのプレイリストに登録することでワールドを更新することなく別の動画を視聴できます。   

iwasync,KineL式につきましては導入補助ツールを作成しております。  
https://aki-lua87.booth.pm/items/3443008   
https://aki-lua87.booth.pm/items/3271864  

一部の動画再生URLについてはQuestでの再生にも対応しております(多分)

## 使い方  

### チャンネル編  
  
チャンネルをシステムで登録することで指定したチャンネルの最新から20個の動画について視聴することができます  
  
チャンネルIDはUCで始まる24桁の文字列です  
  
例:  
SUSURU TV. => UCXcjvt8cOfwtcqaMeE7-hqA  
HikakinTV  => UCZf__ehlCEBPop-_sldpBUQ  


1. チャンネルの登録  
  
下記のAPIをコールします。登録してないチャンネルの動画については取得もできません。  
一度呼び出せば同じチャンネルについては不要になります  
そのため他の人が既に呼んでいる場合などは登録せずとも後述の取得が出来る場合があります。    

URL: https://vrc.akakitune87.net/video/yt/channel/regist  
METHOD: POST  
BODY:  
` {channel_id:[チャンネルID]} `  


2. 動画リストの取得  
  
登録したチャンネルの現在閲覧可能な動画について、VRChat内で参照できるようにするため、動画形式でリストを作成して公開するようにしてます。  
  
画像1.動画リスト  
  
URL: https://vrc.akakitune87.net/videos/yt/chlist/{チャンネルID}  
METHOD: HEAD or GET  

3. 動画の取得  

登録したチャンネルの動画について以下URLで再生できます。
n=0が最新動画で19に近づくほど古い動画になります。
YoutubeDataAPIにて取得した情報を参照しているため、実際のサイトと異なる場合や20より動画数が下回る場合があります。
リンク先に動画が存在しない場合、エラー動画へと飛びます。
  
URL: https://vrc.akakitune87.net/videos/ytlive/ch/{チャンネルID}?n=[0~19の数字]  
METHOD: HEAD or GET  

※Quest対応

4. ライブの取得(β)  
  
もし指定したチャンネルについてライブ配信中である場合下記URLで再生可能です。   
https://vrc.akakitune87.net/videos/ytlive/ch/{チャンネルID}  


### 検索編

1. 動画の取得(β)  

q=の値で指定した検索ワードの結果について再生できます。
n=0が最新動画で19に近づくほど古い動画になります。  
https://vrc.akakitune87.net/videos/yt/query?q=[検索キーワード]&n=[0~19の数字]  

※Quest対応