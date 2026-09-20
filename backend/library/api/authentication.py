from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class LibraryJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user.frozen:
            raise AuthenticationFailed('账号已冻结')
        return user


class LibraryJWTScheme(SimpleJWTScheme):
    target_class = 'library.api.authentication.LibraryJWTAuthentication'
