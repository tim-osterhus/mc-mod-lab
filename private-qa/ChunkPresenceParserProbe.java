package xyz.langyo.minecraft.mcp.common;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** Offline request-contract check; this class is never added to the bridge JAR. */
public final class ChunkPresenceParserProbe {
    private static final Method PARSE;

    static {
        try {
            PARSE = ChunkPresenceHandler.class.getDeclaredMethod("parse", String.class);
            PARSE.setAccessible(true);
        } catch (ReflectiveOperationException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    private static void rejects(String body) throws Exception {
        try {
            PARSE.invoke(null, body);
            throw new AssertionError("invalid request accepted: " + body);
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalArgumentException)
                    && !(expected.getCause() instanceof java.io.IOException)) throw expected;
        }
    }

    public static void main(String[] args) throws Exception {
        String valid = "{\"schema_version\":2,\"kind\":\"observe\",\"name\":\"chunk_presence\","
                + "\"params\":{\"x\":30,\"y\":64,\"z\":-30000000}}";
        Object parsed = PARSE.invoke(null, valid);
        Method x = parsed.getClass().getDeclaredMethod("x");
        Method y = parsed.getClass().getDeclaredMethod("y");
        Method z = parsed.getClass().getDeclaredMethod("z");
        x.setAccessible(true); y.setAccessible(true); z.setAccessible(true);
        if ((int) x.invoke(parsed) != 30 || (int) y.invoke(parsed) != 64
                || (int) z.invoke(parsed) != -30000000) throw new AssertionError("valid coordinates changed");
        rejects(valid.replace("\"x\":30", "\"x\":true"));
        rejects(valid.replace("\"x\":30", "\"x\":30.0"));
        rejects(valid.replace("\"x\":30", "\"x\":\"30\""));
        rejects(valid.replace("\"x\":30", "\"x\":30000001"));
        rejects(valid.replace("\"y\":64", "\"y\":320"));
        rejects(valid.replace("\"x\":30", "\"x\":30,\"x\":30"));
        rejects(valid.replace("\"z\":-30000000", "\"extra\":1"));
        rejects(valid.replace("\"schema_version\":2,", ""));
        rejects(valid.replace("\"schema_version\":2", "\"schema_version\":2,\"schema_version\":2"));
        rejects(valid.replace("\"kind\":\"observe\"", "\"kind\":\"action\""));
        rejects(valid.replace("\"name\":\"chunk_presence\"", "\"name\":\"execute_command\""));
        rejects(valid + "{}");
        System.out.println("private chunk parser: 12 negative controls passed");
    }
}
