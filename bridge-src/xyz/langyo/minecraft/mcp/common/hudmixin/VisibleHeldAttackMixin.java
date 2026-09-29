package xyz.langyo.minecraft.mcp.common.hudmixin;

import xyz.langyo.minecraft.mcp.common.ScenarioActions;

import net.minecraft.class_310;
import net.minecraft.class_312;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = class_310.class, remap = false)
public abstract class VisibleHeldAttackMixin {
    @Inject(method = "method_1574", at = @At("HEAD"), remap = false)
    private void lab$expireVisibleAttack(CallbackInfo ci) {
        ScenarioActions.expireVisibleAttack((class_310) (Object) this);
        ScenarioActions.expireVisiblePulse((class_310) (Object) this);
    }

    @Redirect(method = "method_1508", at = @At(value = "INVOKE",
            target = "Lnet/minecraft/class_312;method_1613()Z"), remap = false)
    private boolean lab$heldAttackGrabGate(class_312 mouse) {
        return ScenarioActions.permitsHeldAttackWithoutGrab((class_310) (Object) this)
                || mouse.method_1613();
    }
}
