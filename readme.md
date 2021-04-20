# 使用メモ

URL:
https://demv79t9nj.execute-api.ap-northeast-1.amazonaws.com/prod/

## 1. ユーザ登録

- req
    - POST /user/register
    - Body特になし

- res
```
{
    "user_id": "hogehoge"
}
```


## 2. 動画登録

- req
    - POST /users/{user_id}/video/register
```
{
    "video_url": "hogehoge",
    "description": "説明"
}
```

- res
```
{
    "video_id": "hogehoge"
}
```

## 3. 動画更新

- req
    - POST /users/{user_id}/video
```
{
    "video_id": "{video_id}",
    "video_url": "hogehoge",
    "description": "説明"
}
```

- res(Body無し)
```

```

## 4. 動画ページ取得
(VRChatの動画プレイヤーのURLに入力する利用を想定)

/users/{user_id}/video?video_id={video_id} にアクセス
