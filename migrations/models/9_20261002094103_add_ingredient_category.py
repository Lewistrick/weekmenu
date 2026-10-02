from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


# SQLite cannot ``ADD CONSTRAINT``, so the foreign key is declared on the
# column itself (aerich generated a separate ``ADD CONSTRAINT`` statement).
async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "ingredientcategory" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL,
    "sort_order" INT NOT NULL DEFAULT 0,
    "owner_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ingredientc_owner_i_3a6cf5" UNIQUE ("owner_id", "name")
) /* A user-defined grocery category (vegetables, freezer, ...). */;
        ALTER TABLE "ingredient" ADD "category_id" INT REFERENCES "ingredientcategory" ("id") ON DELETE SET NULL;
        ALTER TABLE "userpreference" ADD "categories_seeded" INT NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "ingredient" DROP COLUMN "category_id";
        ALTER TABLE "userpreference" DROP COLUMN "categories_seeded";
        DROP TABLE IF EXISTS "ingredientcategory";"""


MODELS_STATE = (
    "eJztXWtzozYX/isavx+azDiZbnqdfkuybuu32Xgnl7edNh1WBtlmAhKLIFm33f/+6nAxN4"
    "GNjTHUyszuZkFHwIM4es5FR38PbGYQi5//5DKduMsbk3tjj9iDH9DfA4ptIn4pazJEA+w4"
    "SQM44OGpFcjMw8aWaGzGjafcc7HuidMzbHEiDhmE667peCajIDShBFmm+ItRhJHPifsFR0"
    "LCfCEo6hBBj+fQncF00Z9J57UlfWp+9InmsTnxFsQV8n/8MQAZOCk6dIlhEupFTb3Bn38G"
    "xw3yiXBoDP91nrWZSSwjA5RpgExwXPOWTnBsTL0fg4Zwy1NNZ5Zv06Sxs/QWjK5am+Fl54"
    "QSF3sEuvdcH6CivmVF4Mbohc+RNAlvMSVjkBn2LQAcpAt4xwdTQEaHdEbhXYm74cEDzuEq"
    "Zxdvvv7u6++/+vbr70WT4E5WR777HD5e8uyhYIDA7cPgc3AeezhsEcCY4PbRx1QMk2URvR"
    "8thkvwSwvlUJyBVB7HGLUqIOMDCZLJSG0Gygqc3k4er25G6P3d6Hp8P57cwgPYS/7RSk7C"
    "IXFAfFFw7G50eRMgmyDJPez5vIjjA/lUAmMikQNR3PW+IByEX+ZgLzA+jH57CKDjEXS3/7"
    "u8u/758u7k3eVvpxlQbya3P8XNmVBNoeq6vb6ZXOVwNemL0AjMXWpbjVW5eJuj9svODtlE"
    "4Wr19Gdebr0q7YYKaEabpr75BXPqQZeS2Aq0aHrpMWYwr9fDLCVxrAMNKFJN0BKJYwINCO"
    "LsWUp1YpqZmzqYS8w5/YUsAxzH4o4w1YkEt4iLP0bddA+/z/EYiI8m+sLFryvSnB4a4vHE"
    "Q5Fwhri+vL++fDsalMwRDWA3znTWXwQLE+B6HANzpoHRF3XTX+xS2nw9ajBdNoDafdRN5y"
    "bXTUFL0YYMaPejB3T7eCOIHSi+KdafX7FraBkNCGfYBcsdWbUtnrIv7PwRTPE8AAAeA266"
    "+EFL3BbZz73cY5HVMeudFZd0iRIZdOIxhA0DxQQfYWogGGZDxAlBd0Q3HZLcy2nRh9FEhx"
    "LXhnJe7Nd5EfxbQK7c4I7bt2du781jsRdTWxdPPwdTudaAzEkdqVnDXmldip4WURw9QVGR"
    "9NzgWM+T4m+wUY5+neq0c9/vpjjmtFNt9pRgHAUzNAhmaBBZkTh7r6I+fvzljlg4eKZSoC"
    "VBnf4M1xIXbQOwjOPOeg9KueFcB4882+wxJIHjAUyZHYcIaPcEkA2Nu66C8krIs7XUQu1i"
    "kh2h+TXoLVItPUOlHUN1NatVGqzpuW8TwzU9AW9gwAZx8jOBqEmJsQqTx52gkxcirEi4Ch"
    "+imUvIX8QdovPzc5ntun1fT/SJwvTDQcp3UKC90TQlbFL04QNnrqcx1yDuhw/CAmYIPmFH"
    "XD6wi/UF0Z/Ff56oMHuR7jtTJt4WF31QNGeIUSKMZh2eHGEPYeSZNinPBVgRwODNqPC/sq"
    "B7ZUEnn0qdmGBGqD1LcIfAtLKelfXcJe4wrG09b2LxJdP7zjZNDfbeHVt6z4wsbedJyVjO"
    "EKziYVHTzRMeLwUdsZlPPcRmAUlJ+/8F7YFD4PI/jZIa0QJzoEPcY/ozMJkFi3hMLpLQRL"
    "dAzH5dEEioTKdQIlMwtXjwDIOsS45mAlbB2NgLEdcB8rYCA2GXIFucMAQ3YwjoGbZcgo3l"
    "2QK/kLBLoHDBmfCuxRVcIu5LCKET7k8DFIlxKpgjs5GgaZtwN5XI2T6T61UiZ3dT4nTxfY"
    "hn1bDEa/NWnAHrpSQMkpHMoWlEoufxL92cXgegHSbUWg5WjopS+jx+N7p/uHz3PsOh314+"
    "jODMRRb76OjJt6dZCr3qBP06fvgZwX/R75Pb4DU5jHtCjfBMu4ffwe89wL7HNMpeNWykPt"
    "X4aAxM1vfkGFu+2KykerEHfbEVblaVw6pML5XG2jnQlL3aeLRX5WSqnMxGsVubk3mY7MIw"
    "9DmQ+AaiM8Mqp4CbtNkgIBO2RjPmoiXzXWFQs+ep+CMLuFS2VXmAKorR8yhG+jZrwJoTU+"
    "iWLGi0hbbTfNeqg21GaCtkD+ZWbg1YxyWOBja4ZpvU92SpFKXaVCp7TDQ94wQTc9m2QEpl"
    "jxVIcKSL69XBLy1yrLA5rvkiHlASc2PMIpiWfcIrqRxwgptZ+0JuRZWaVpFXk8lNRkVejf"
    "M68PHd1eju5M1p1qtdxJNQeEIJuazEMyWl8CwGCVhNp1lW6EhXSZi2w1xwpkM4sabDViJ6"
    "pCgql63yPh7O+xgpsvaQ605CTB64rE4vWVtSqv8aQDDxg/UWQ5le32GVTtjdjvlaPYQ1M8"
    "wS16dad/IDuITnczHAmkPlAc97DAesONFsQn2NW2zXTwUWnLwTfd2Lrvr1wew/clFdHUH2"
    "ga2LZtSvlJBOQDQhoTAKXgTlIel8KA7qlm/Aao5CuQNpeuOu/an4iMoN7G2RR5VttNXQzD"
    "OTeuBlZI4VOJVvtLvFX0YA92d2dYgCDnN2V+arUjlHKudI5RxlDbxSyh5Zf+u4uhc12yD5"
    "SDSF1TzPxEBQemy1/lqWfFTZVpHr1sm1YjRbMhoxkOuhlggcE2SKz+yFz0TaeUfgeucIzK"
    "OWfFNdmoSDkj6S+Tcu9VM+9cYFYzeZdeOltSCDXk1vgQyTOxaG1bQW810eZPjC4tjMItzH"
    "sWxa3q0zNW+rpOGeZ1+K4U2gjBA1ADRZfLgcW5lsi3ui/GcW/Az6Azao2W3Blsm2CfbFN9"
    "9+RaY9Alul26h0m3bTbTZJdDh8OdIOxXKLe6U0Vbpnq1qTHUJmnzS9xEu21j9W0zM2JRaj"
    "c4goBw6v0NArc43JG0NBnfA81NvBCO44CEun/GfQZlX4EP2DyCdsOxYBKf5Ez+Ifceas7O"
    "eJcoI5owhBB9y3bai1+CpeB/yL6XKIiKefw3XcaTDSRDOHedhjQ+SauoDAwUIBxs3EmPMQ"
    "Cnt7IXNMh8KKMGzshA2U5aAsh/3pktb41eG2Hegpy1LktGly2mD9fDH71Sic32GaWlU5X+"
    "pSVQy/WYa/CiM2ks3cO1d1Sc5qWnonWOLMVfhgk2srci/RY3KSv1mNdDF+6xZHX7FwNgvY"
    "t4zrS9soMqzIcM/JsHKjKze6cqMrS0W50dsh2eWWXx0uqch1Q+S6SxDtk10/jmFmGUiIdX"
    "SmklP7phe3WUunb5iOLfMvYqDHMQqhgGrzUCzepEFCCnC7KeYEODW22LxIt7fsQ1ol3sJ0"
    "7kMxK108F7R6JktVHn7fNL2A+qY0pyCoiLuc3sAwroFr1FyhKUcz1m+bwhm3V3gmeBZY5G"
    "GSOYOlKrKJLlrCUjHNxS022VBPtAVfkE0w911iw/pkyLjEZSuWh4icz8+RYxIddsabu9jm"
    "sKeKR1ypw6n5CyhvVevTIJ5OXfJSR7EkEkq1lOx5J27GqsUpEglVyVReydTyXVyrPmwioS"
    "BV3iflfeqJ9+nwSZwdgji33lztKV9MbZUuHj/Sql5q4/RBG45KHlgmRest0uAV1lvcYqO9"
    "OB3HMvXgHYX7Yr4uGBI6lkfGFA+ydVcbjzsumRGXiDlGZqvt3J2yzFq3zOAt1c0lSMso60"
    "zOe4mNzVqWxEpAGRJy2wxz/sqEWl1gvqhlouUFFcDy/VG4hg3blGw9U1muPi3WYr16+ZTW"
    "BLgNFqy3fWFe6AtM50SLh2FNeMu6UFDXcrQr028T06+htXv/CjMnVWMsylXZ2dZJcOnnSg"
    "XlKFgHSrwZeWTtNOEz6DI32aQaelsgdHVIgLG7IwYbrn7uKgK7r6Tpd5of1Hpqagrp7Sq3"
    "gj911/oAvSvEWcYuGlAQWxVL6Co0iVNwd1DeZ/rqKSCH3Dei+5io1GkVpzlwnCanekuiNk"
    "UFXR3DSZnjGxdXfBtCGVZDxJybc1qSMAdxdANNlwgHgZpiNGe3rlQkp/VIjtojYytAs5Za"
    "PehSEke6JWZY9KvW9hhcJXcNCiFYlduVHRpqY4y2NsaIycWOCPauQl8eupQu71JJ7pwVW8"
    "Its3ZuNa/M2tfrOeV74p4FuTxY15kv+B6k8IBxcQb2VzqHBznE5Sb3issTi/SysV4V0zzY"
    "osY6WRhpmRbLNTz5xvdf6eJvg+ip379DIzq3zDAfpCf5GdFTaeKjeRH3JbHnS8euTLQ98n"
    "Vx6JGcmuw87HqagWstGc0ItTh2bUaji/ZkhIZbkBLN8aeWqdfNIyoIqxSXLLzZzBVqemZY"
    "HKAm0FXdKMilJVJNwoXuJEZtrKXyCmTlQ/iX+RD2zWgb8yAcxojLBN0kJlw+KFduwIGFBA"
    "YSj1uuNd8mFAymZbhCHvD5ggd2FoJuinbZ+ubS6jLx+APCoorK7Nn+qslfW2eujXzr7S0s"
    "MCmtPbEnQmo2z5lY9c3TozdLD7OXqYo+KeZ4cObYnQBArehT+1vAdjdyUr4D7P3oAd0+3t"
    "wcmndnU7oqCHgh92s9E4c661mRtZRcXOUMShg7KJEM8mpWRBu5mBrMNv8KsrKKLH2rHiqJ"
    "+6oeq2Lve2bvds1KkHH7Fj3PrFfVxG2TmrZva0EcscaYLMi1xwjeHHp4ql2gGgEv2cZ7Q9"
    "wSAUXZFWVXlL1Fyq72Gmtgr7FoC9Hd8eukstsUtkSLd87cSdZolJg5mUUc1eaNtZynmm5Q"
    "DFhYgr4bVKmPBKMYApr6S47ICxyBjofIpy4sOSEGbBcLOV0VIYmG+oV9ZkMA0GpNDBKvLu"
    "7rmRBH/A7ZZoxiC0F8HAoPi8HsWKLpyavpLdBHH1PP9JZPFBLWYCHjqbgO9pCOKZoShA0j"
    "vDimy9XdBl2ZFDEqGuhVBpkyvvZrfMWvT6LELIZL8EsL5VCcgVSn5wAZTm8nj1c3I/T+bn"
    "Q9vh9PbjOGV3gy6+a/G13eFJJ91HITtYPsAQwIoXJrGhCJxDGBVmFAqHLCMZNbX05YrTlp"
    "fs2JvJ5u/eHXuxoQeexSqqlL+UqXghzri4HEgojOVJoOOGmzzmYoB1Rx49a58Quss2GS+o"
    "/XC+zK0UuJ9CW9SIz6T5pF6NyDAX7xzTcVmMXBCdHqNBeHiE5dhOeyFAU+jRogRs37CeCb"
    "L7/cAEDRqhTA4FwuJsGoJ51k/3s/uS0JSCQiOSDFLMHoH4ape8PAEP+zm7BWoAhPXR01yw"
    "fIAAXGPTEx87iDg+9M9fn/o/UzwQ=="
)
